"""Verify the Topic 06 byte patch against the official 7za.exe (step 1).

Checks performed, all on copies (the original EXE is never modified):
  1. SHA-256 of the original 7za.exe equals the published 26.06 x64 hash.
  2. topic06.1337 is parsed, each RVA is converted to a file offset through
     the PE section table and each "old" byte is checked before writing "new".
  3. The .1337 result is compared byte-for-byte with the EXE that
     reproduce.py builds from its embedded BEFORE/AFTER bytes.
  4. Every byte that differs from the original lies inside the 24-byte window
     at RVA 0x777C8 / file offset 0x76BC8, and exactly 17 bytes change.
  5. Optional: a 24-byte x64dbg `savedata` export and/or candidate EXEs (for
     example the file written by x64dbg GUI "Patch file") are checked too.

Example:
    python verify_patch.py --original x64\\7za.exe --write-1337 7za-1337.exe
"""
import argparse
from pathlib import Path
import sys

import reproduce
from topic06_common import pe_layout, rva_to_offset, sha256_bytes

PATCH_RVA = 0x777C8
PATCH_LEN = len(reproduce.BEFORE)
EXPECTED_CHANGED = 17
HERE = Path(__file__).resolve().parent

# Instruction view of the 24-byte window (identical in objdump, Ghidra, x64dbg).
BEFORE_ASM = [
    (0x00, "88 91 9A 00 00 00", "mov byte ptr [rcx+0x9A], dl"),
    (0x06, "88 91 9B 00 00 00", "mov byte ptr [rcx+0x9B], dl"),
    (0x0C, "88 91 9C 00 00 00", "mov byte ptr [rcx+0x9C], dl"),
    (0x12, "88 91 9D 00 00 00", "mov byte ptr [rcx+0x9D], dl"),
]
AFTER_ASM = [
    (0x00, "89 91 9A 00 00 00", "mov dword ptr [rcx+0x9A], edx   ; edx == 0 (xor edx,edx at RVA 777A0)"),
    (0x06, "C7 41 28 03 00 00 00", "mov dword ptr [rcx+0x28], 3     ; default level = 3 (Fast)"),
] + [(0x0D + i, "90", "nop") for i in range(11)]


def parse_1337(path):
    lines = [l.strip() for l in path.read_text(encoding="ascii").splitlines() if l.strip()]
    if not lines or not lines[0].startswith(">"):
        raise RuntimeError("A .1337 file must start with >module.")
    module = lines[0][1:]
    entries = []
    for line in lines[1:]:
        address, change = line.split(":")
        old, new = change.split("->")
        entries.append((int(address, 16), int(old, 16), int(new, 16)))
    return module, entries


def diff(a, b):
    if len(a) != len(b):
        raise RuntimeError(f"Size differs: {len(a)} vs {len(b)} bytes.")
    return [i for i in range(len(a)) if a[i] != b[i]]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--original", type=Path, required=True, help="Official 26.06 x64 7za.exe.")
    parser.add_argument("--patch-file", type=Path, default=HERE / "topic06.1337")
    parser.add_argument("--write-1337", type=Path, help="Write the .1337-applied copy here.")
    parser.add_argument("--x64dbg-export", type=Path, help="24-byte file written by x64dbg savedata.")
    parser.add_argument("--write-x64dbg", type=Path, help="Write original + spliced x64dbg export here.")
    parser.add_argument("--candidate", type=Path, action="append", default=[],
                        help="Extra patched EXE to check (e.g. x64dbg GUI Patch file output).")
    parser.add_argument("--report", type=Path, help="Also write the report to this file.")
    args = parser.parse_args()

    out = []
    failures = []

    def say(text=""):
        out.append(text)
        print(text, flush=True)

    def check(ok, text):
        say(f"[{'PASS' if ok else 'FAIL'}] {text}")
        if not ok:
            failures.append(text)

    original = args.original.read_bytes()
    say("Topic 06 patch verification")
    say(f"Python {sys.version.split()[0]}")
    say(f"Original: {args.original.name} ({len(original)} bytes)")
    say(f"  SHA-256 {sha256_bytes(original)}")
    check(sha256_bytes(original) == reproduce.ORIGINAL_SHA, "Original SHA-256 equals the official 7-Zip Extra 26.06 x64 7za.exe")

    image_base, layout = pe_layout(original)
    offset, section = rva_to_offset(layout, PATCH_RVA)
    say(f"Image base {image_base:#x}; patch VA {image_base + PATCH_RVA:#x}; section {section}")
    check(offset == reproduce.OFFSET == 0x76BC8, f"RVA 0x{PATCH_RVA:X} maps to file offset 0x{offset:X} (expected 0x76BC8)")
    check(original[offset:offset + PATCH_LEN] == reproduce.BEFORE, "Original 24 bytes equal reproduce.BEFORE")

    # Apply topic06.1337 on a copy.
    module, entries = parse_1337(args.patch_file)
    say()
    say(f"{args.patch_file.name}: module {module}, {len(entries)} entries")
    check(module.lower() == "7za.exe", "Patch module is 7za.exe")
    applied = bytearray(original)
    mismatched = []
    for rva, old, new in entries:
        file_offset, _ = rva_to_offset(layout, rva)
        if applied[file_offset] != old:
            mismatched.append(rva)
        applied[file_offset] = new
    check(not mismatched, "Every .1337 'old' byte matches the original EXE"
          + (f" (mismatch at {', '.join(f'{r:X}' for r in mismatched)})" if mismatched else ""))
    applied = bytes(applied)

    expected = original[:reproduce.OFFSET] + reproduce.AFTER + original[reproduce.OFFSET + PATCH_LEN:]
    say(f"reproduce.py EXE SHA-256 {sha256_bytes(expected)}")
    say(f".1337 EXE SHA-256        {sha256_bytes(applied)}")
    check(applied == expected, ".1337-applied EXE is byte-identical to the EXE built by reproduce.py")
    check(sha256_bytes(applied) == reproduce.PATCHED_SHA, "Patched SHA-256 equals reproduce.PATCHED_SHA")

    changed = diff(original, applied)
    window = range(offset, offset + PATCH_LEN)
    check(all(i in window for i in changed), f"All {len(changed)} changed bytes lie in file offsets 0x{offset:X}-0x{offset + PATCH_LEN - 1:X}")
    check(len(changed) == EXPECTED_CHANGED, f"Exactly {EXPECTED_CHANGED} bytes change inside the {PATCH_LEN}-byte window")

    say()
    say("Byte comparison (file offset / RVA / before / after)")
    for i in window:
        mark = "*" if original[i] != applied[i] else " "
        say(f"  {mark} {i:06X}  {i - offset + PATCH_RVA:05X}  {original[i]:02X} -> {applied[i]:02X}")
    say()
    say("Before (RVA 777C8):")
    for rel, raw, text in BEFORE_ASM:
        say(f"  {PATCH_RVA + rel:05X}  {raw:<21} {text}")
    say("After (in-place instruction replacement with NOP padding):")
    for rel, raw, text in AFTER_ASM:
        say(f"  {PATCH_RVA + rel:05X}  {raw:<21} {text}")

    if args.write_1337:
        args.write_1337.write_bytes(applied)
        say(f"\nWrote {args.write_1337.name}")

    if args.x64dbg_export:
        exported = args.x64dbg_export.read_bytes()
        say()
        say(f"x64dbg savedata export: {args.x64dbg_export.name} ({len(exported)} bytes) {exported.hex(' ').upper()}")
        check(exported == reproduce.AFTER, "x64dbg export equals reproduce.AFTER")
        spliced = original[:offset] + exported + original[offset + len(exported):]
        say(f"  spliced EXE SHA-256 {sha256_bytes(spliced)}")
        check(spliced == expected, "Original + x64dbg export is byte-identical to the reproduce.py EXE")
        if args.write_x64dbg:
            args.write_x64dbg.write_bytes(spliced)
            say(f"  wrote {args.write_x64dbg.name}")

    for candidate in args.candidate:
        data = candidate.read_bytes()
        say()
        say(f"Candidate: {candidate.name} ({len(data)} bytes)")
        say(f"  SHA-256 {sha256_bytes(data)}")
        same_size = len(data) == len(original)
        check(same_size, "Candidate has the same size as the original")
        if same_size:
            cdiff = diff(original, data)
            say(f"  differing offsets: {', '.join(f'{i:X}' for i in cdiff) or 'none'}")
            check(all(i in window for i in cdiff), "Candidate differs from the original only inside the patch window")
        check(data == expected, "Candidate is byte-identical to the reproduce.py EXE")

    say()
    say("RESULT: " + ("PASS" if not failures else f"FAIL ({len(failures)} checks)"))
    if args.report:
        args.report.write_text("\n".join(out) + "\n", encoding="utf-8")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
