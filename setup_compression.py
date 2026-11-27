"""Install the original and PPMd-patched 7za.exe into this project's bin directory."""
import argparse
import os
from pathlib import Path
import platform
import subprocess
import tempfile

from topic06_common import ORIGINAL_SHA, obtain_original, pe_layout, require, rva_to_offset, sha256, sha256_bytes


PATCH_RVA = 0x78339
PATCH_OFFSET = 0x77739
BEFORE = bytes.fromhex("8D 53 05 83 F9 FF 0F 44 CA")
AFTER = bytes.fromhex("4C 8D 2D A0 4E 08 00 90 90")
PATCHED_NAME = "7za-ppmd.exe"
PATCHED_SHA = "1cb1b0b4546dc11598a2ea3a22a639e475c2d33b8f7b8a94e304a3a18faa6b19"
HERE = Path(__file__).resolve().parent


def patch_binary(original, replacement=AFTER):
    binary = original.read_bytes()
    require(sha256_bytes(binary) == ORIGINAL_SHA, "Unexpected original executable SHA-256.")
    _, sections = pe_layout(binary)
    offset, section = rva_to_offset(sections, PATCH_RVA)
    stop = offset + len(BEFORE)
    require((offset, section) == (PATCH_OFFSET, ".text") and binary[offset:stop] == BEFORE,
            "Unexpected original method-selection instructions.")
    require(replacement == AFTER, "The x64dbg export differs from the expected 9 patch bytes.")
    patched = binary[:offset] + replacement + binary[stop:]
    require(sha256_bytes(patched) == PATCHED_SHA, "Unexpected patched executable SHA-256.")
    return patched


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, help="Use an offline copy of the official 7z2606-extra.7z.")
    parser.add_argument("--output-dir", type=Path, default=HERE / "bin")
    parser.add_argument("--x64dbg-export", type=Path, help="Verify and use the 9 bytes exported by x64dbg.")
    args = parser.parse_args()
    require(os.name == "nt" and platform.machine().upper() in {"AMD64", "X86_64"}, "Run on Windows x64.")
    package = args.package.resolve() if args.package else None
    destination = args.output_dir.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="setup-", dir=destination) as stage_name:
        stage = Path(stage_name)
        original = obtain_original(stage, package)
        package = package or stage / "7z2606-extra.7z"
        replacement = args.x64dbg_export.read_bytes() if args.x64dbg_export else AFTER
        patched = stage / PATCHED_NAME
        patched.write_bytes(patch_binary(original, replacement))
        subprocess.run(["tar", "-xf", str(package), "License.txt"], cwd=stage, check=True)
        artifacts = (original, patched, stage / "License.txt")
        for file in artifacts:
            target = destination / file.name
            if target.exists():
                require(target.is_file() and sha256(file) == sha256(target),
                        f"Existing file differs: {target}. Choose another --output-dir.")
        for file in artifacts:
            target = destination / file.name
            if not target.exists():
                file.rename(target)
            print(f"{sha256(target)}  {target}")
        print(f"Package SHA-256: {sha256(package)}")
        print(f"Patch source: {'verified x64dbg export' if args.x64dbg_export else 'verified embedded bytes'}")


if __name__ == "__main__":
    main()
