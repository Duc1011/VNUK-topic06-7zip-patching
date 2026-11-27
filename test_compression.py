"""Exercise the PPMd-patched EXE and the PowerShell CLI on Windows x64."""
import argparse
from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

from benchmark_compression import build_fixtures, manifest, measure, run_command, write_json
from setup_compression import HERE, PATCHED_NAME, PATCHED_SHA, patch_binary
from topic06_common import ORIGINAL_SHA, require, sha256


def verify_direct(lab, logs, original, patched, source):
    expected = manifest(source)
    configs = {
        "original-default": (original, []),
        "original-ppmd5": (original, ["-m0=PPMd", "-mx=5"]),
        "original-ppmd9": (original, ["-m0=PPMd", "-mx=9"]),
        "original-copy": (original, ["-mx=0"]),
        "patched-default": (patched, []),
        "patched-m0": (patched, ["-m0=LZMA2"]),
        "patched-mx": (patched, ["-mx=9"]),
        "patched-copy": (patched, ["-mx=0"]),
    }
    rows = {name: measure(lab, logs, original, source, name, exe, options, expected)
            for name, (exe, options) in configs.items()}
    pairs = {
        "patched-default": ("original-ppmd5", "PPMD"),
        "patched-m0": ("original-default", "LZMA2"),
        "patched-mx": ("original-ppmd9", "PPMD"),
        "patched-copy": ("original-copy", "Copy"),
    }
    for name, (reference, method) in pairs.items():
        row = rows[name]
        row["matches_reference"] = row.get("archive_sha256") == rows[reference].get("archive_sha256")
        row["expected_method"] = method
        row["reference"] = reference
        row["verified"] &= row["matches_reference"] and (row.get("method") or "").startswith(method)
    return rows


@contextmanager
def exclusive_read_lock(path):
    # Force a real reproducible failure for every 7za process without altering either EXE.
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                       wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = create(str(path), 0x80000000, 0, None, 3, 0, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        yield
    finally:
        kernel.CloseHandle(handle)


def run_with_candidate_collision(command, lab, temp, log):
    # Insert a directory at the second archive's path while the baseline is compressing.
    # The EXEs, sources, initial arguments and production script are the same as a normal run.
    env = dict(os.environ, TMP=str(temp), TEMP=str(temp))
    injected = False
    with subprocess.Popen(list(map(str, command)), cwd=lab, env=env, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace") as process:
        while process.poll() is None and not injected:
            for work in temp.glob("topic06-compress-*"):
                try:
                    (work / "candidate-2.7z").mkdir()
                    injected = True
                    break
                except (FileExistsError, FileNotFoundError):
                    continue
            if not injected:
                time.sleep(0.01)
        output, _ = process.communicate(timeout=180)
    log.write_text(subprocess.list2cmdline(list(map(str, command))) +
                   f"\nExit code: {process.returncode}\nInjected directory at candidate-2.7z: {injected}\n\n" + output,
                   encoding="utf-8")
    require(injected, "Did not intercept the second candidate archive path.")
    return process.returncode, output


def verify_cli(lab, logs, original, fixtures, powershell, binaries):
    outputs = lab / "Kết quả nén"
    outputs.mkdir()
    temp = lab / "fault-injection-temp"
    temp.mkdir()
    prefix = [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", HERE / "Compress-Topic06.ps1"]
    rows = {}

    def check_case(name, source, output, expected_winner=None, expected_error=None, inject=False):
        prior = sha256(output) if output.is_file() else None
        expected = manifest(source) if source.exists() and name != "all-fail-locked" else None
        command = [*prefix, "-Source", source, "-Output", output, "-BinaryDirectory", binaries]
        log = logs / f"{name}-cli.txt"
        if inject:
            code, text = run_with_candidate_collision(command, lab, temp, log)
        else:
            result, _ = run_command(command, lab, log)
            code, text = result.returncode, result.stdout + result.stderr
        leftovers = [str(p.relative_to(lab)) for pattern in ("topic06-compress-*", ".topic06-*.tmp")
                     for p in lab.rglob(pattern)]
        row = {"exit_code": code, "leftovers": leftovers}
        if expected_error:
            row.update(expected_message=expected_error, message_found=expected_error in text,
                       destination_untouched=sha256(output) == prior if prior else not output.exists())
            row["verified"] = code != 0 and row["message_found"] and row["destination_untouched"] and not leftovers
        elif code == 0 and output.is_file():
            with tempfile.TemporaryDirectory(prefix="restore-", dir=lab) as extracted_dir:
                extracted = Path(extracted_dir)
                result, _ = run_command([original, "x", "-sccUTF-8", f"-o{extracted}", "--", output],
                                        lab, logs / f"{name}-extract.txt")
                restored = extracted / source.name
                actual = manifest(restored) if restored.exists() else {}
                source_after = manifest(source)
                if source.is_dir() and output.is_relative_to(source):
                    source_after.pop(output.relative_to(source.parent).as_posix(), None)
                match = actual == expected and [p.name for p in extracted.iterdir()] == [source.name]
                write_json(logs / f"{name}-manifest.json", {"matches": match, "source": expected, "extracted": actual})
            sizes = {label: int(count) for label, count in re.findall(
                r"(?m)^(Original default|Patched default|PPMd Ultra)\s+\S+\s+(\d+)\s+PASS\s*$", text)}
            match = match and result.returncode == 0
            row.update(winner=expected_winner, archive_bytes=output.stat().st_size, candidates=sizes,
                       baseline_bytes=sizes.get("Original default"), extract_exit_code=result.returncode,
                       paths_and_sha256_match=match, source_unchanged=source_after == expected,
                       candidate_failure_observed=inject and bool(re.search(r"Patched default\s+-\s+Create failed \([1-9]\d*\)", text)))
            row["verified"] = (match and row["source_unchanged"] and not leftovers and
                               f"Selected {expected_winner} (" in text and
                               len(sizes) == (2 if inject else 3) and
                               row["archive_bytes"] == sizes[expected_winner] == min(sizes.values()) and
                               (not inject or row["candidate_failure_observed"]))
        else:
            row["verified"] = False
        rows[name] = row
        print(name, row, flush=True)

    single = fixtures["fixture64"].with_name("@ Bản ghi 64 MiB.txt")
    fixtures["fixture64"].rename(single)
    check_case("single-text", single, outputs / "Tệp lớn.7z", "PPMd Ultra")
    text_tree = fixtures["text-logs"]
    nested = text_tree / "Bản sao.7z"
    check_case("unicode-tree-output-inside", text_tree, nested, "Patched default")
    if nested.exists():
        nested.rename(outputs / nested.name)
    check_case("precompressed-zip", fixtures["compressed-zip"], outputs / "Tệp ZIP.7z", "Original default")
    check_case("missing-source", lab / "Không tồn tại.txt", outputs / "Missing.7z",
               expected_error="Source file or directory does not exist")
    existing = outputs / "Existing.7z"
    existing.write_bytes(b"existing destination")
    check_case("existing-output", single, existing, expected_error="Output already exists")
    check_case("one-candidate-fails", text_tree, text_tree / "Sau lỗi.7z", "PPMd Ultra", inject=True)
    locked = lab / "Locked.txt"
    locked.write_bytes(b"contents held with an exclusive sharing mode")
    with exclusive_read_lock(locked):
        check_case("all-fail-locked", locked, outputs / "Locked.7z", expected_error="No valid archive")
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--binary-directory", type=Path, default=HERE / "bin")
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--powershell", type=Path, default=Path(os.environ.get("SystemRoot", r"C:\Windows")) /
                        "System32/WindowsPowerShell/v1.0/powershell.exe")
    args = parser.parse_args()
    evidence = args.evidence_dir.resolve()
    evidence.mkdir(parents=True)
    direct_logs = evidence / "direct"
    cli_logs = evidence / "cli"
    direct_logs.mkdir()
    cli_logs.mkdir()
    binaries = args.binary_directory.resolve()
    original, patched = binaries / "7za.exe", binaries / PATCHED_NAME
    require(sha256(original) == ORIGINAL_SHA and sha256(patched) == PATCHED_SHA and
            patch_binary(original) == patched.read_bytes(), "EXE hash or patch bytes do not match.")
    with tempfile.TemporaryDirectory(prefix="topic06-tests-", dir=Path.cwd()) as work:
        lab = Path(work)
        fixtures = build_fixtures(lab, args.fixture)
        direct = verify_direct(lab, direct_logs, original, patched, fixtures["text-logs"])
        write_json(evidence / "direct-results.json", direct)
        cli = verify_cli(lab, cli_logs, original, fixtures, args.powershell, binaries)
        write_json(evidence / "cli-results.json", cli)
    require(all(row["verified"] for row in [*direct.values(), *cli.values()]), "A verification case failed.")
    print(f"Verified {len(direct)} direct EXE cases and {len(cli)} PowerShell CLI cases.")


if __name__ == "__main__":
    main()
