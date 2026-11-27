"""Reproduce Topic 06 with Python 3 on Windows x64."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
# Allow direct execution from this folder with the shared release helpers at the repo root.
sys.path.insert(0, str(HERE.parent))
from topic06_common import ORIGINAL_SHA, generate_input, obtain_original, require, sha256


PATCHED_SHA = "985d511efd476fe87d7258e61abb3e99a03e7f63915203550bd28a46aae53b98"
OFFSET = 0x76BC8
BEFORE = bytes.fromhex("88 91 9A 00 00 00 88 91 9B 00 00 00 88 91 9C 00 00 00 88 91 9D 00 00 00")
AFTER = bytes.fromhex("89 91 9A 00 00 00 C7 41 28 03 00 00 00") + b"\x90" * 11


def execute(lab, log_name, exe, *args):
    command = [str(exe), *args]
    result = subprocess.run(command, cwd=lab, capture_output=True, text=True, errors="replace")
    (lab / "logs" / f"{log_name}.txt").write_text(
        subprocess.list2cmdline([exe.name, *args])
        + f"\nExit code: {result.returncode}\n\n"
        + result.stdout + result.stderr, encoding="utf-8"
    )
    require(result.returncode == 0, f"{log_name} exited with {result.returncode}.")
    return result.stdout


def compress(lab, original, case):
    name, exe, option = case
    archive = f"{name}.7z"
    args = ["a", "-t7z", "-mmt=1"]
    if option:
        args.append(option)
    execute(lab, name + "-create", exe, *args, archive, "input.txt")
    listing = execute(lab, name + "-list", original, "l", "-slt", archive)
    methods = re.findall(r"^Method = (.+)$", listing, re.MULTILINE)
    require(bool(methods), f"Missing Method field in {name}.")
    return name, {
        "executable": exe.name, "option": option, "exit_code": 0,
        "method": methods[0], "archive_bytes": (lab / archive).stat().st_size,
        "archive_sha256": sha256(lab / archive),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", type=Path, help="Use a verified 26.06 x64 7za.exe.")
    parser.add_argument("--package", type=Path, help="Use a local 7z2606-extra.7z package.")
    parser.add_argument("--patched", type=Path, help="Test a prebuilt copy exported by x64dbg.")
    parser.add_argument("--work-root", type=Path, default=HERE)
    parser.add_argument("--jobs", type=int, default=1, choices=range(1, 7))
    parser.add_argument("--evidence-dir", type=Path,
                        help="Copy results.json and logs/ here after a successful run (e.g. evidence).")
    args = parser.parse_args()
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    require(os.name == "nt" and platform.machine().upper() in {"AMD64", "X86_64"},
            "Run this experiment on Windows x64.")
    lab = Path(tempfile.mkdtemp(prefix="topic06-", dir=args.work_root.resolve()))
    print(f"Experiment folder: {lab}", flush=True)
    (lab / "logs").mkdir()
    original = args.original.resolve() if args.original else obtain_original(
        lab, args.package.resolve() if args.package else None
    )
    require(sha256(original) == ORIGINAL_SHA, "Unexpected original executable SHA-256.")
    binary = original.read_bytes()
    require(binary[OFFSET:OFFSET + len(BEFORE)] == BEFORE, "Unexpected original patch bytes.")
    patched = lab / "7za-patched.exe"
    expected = binary[:OFFSET] + AFTER + binary[OFFSET + len(BEFORE):]
    produced = args.patched.read_bytes() if args.patched else expected
    require(produced == expected, "Patched file differs outside the validated byte edit.")
    patched.write_bytes(produced)
    require(sha256(patched) == PATCHED_SHA, "Unexpected patched executable SHA-256.")
    input_file = lab / "input.txt"
    generate_input(input_file)
    cases = [
        ("T01", original, None),
        ("T02", original, "-mx=3"),
        ("T03", original, "-mx=5"),
        ("T04", patched, None),
        ("T05", patched, "-mx=5"),
        ("T06", patched, "-mx=0"),
    ]
    with ThreadPoolExecutor(max_workers=args.jobs) as workers:
        rows = dict(workers.map(lambda case: compress(lab, original, case), cases))
    execute(lab, "T07-test", original, "t", "T04.7z")
    execute(lab, "T07-extract", original, "x", "T04.7z", "-oextracted")
    input_hash = sha256(input_file)
    extracted_hash = sha256(lab / "extracted" / "input.txt")
    fast = rows["T02"]
    normal = rows["T03"]
    hashes_differ = fast["archive_sha256"] != normal["archive_sha256"]
    rows["T01"]["pass"] = rows["T01"]["archive_sha256"] == normal["archive_sha256"]
    rows["T02"]["pass"] = hashes_differ and fast["method"] == "LZMA2:22"
    rows["T03"]["pass"] = hashes_differ and normal["method"] == "LZMA2:25"
    rows["T04"]["pass"] = rows["T04"]["archive_sha256"] == fast["archive_sha256"]
    rows["T05"]["pass"] = rows["T05"]["archive_sha256"] == normal["archive_sha256"]
    rows["T06"]["pass"] = rows["T06"]["method"] == "Copy"
    rows["T07"] = {"test_exit_code": 0, "extract_exit_code": 0,
                   "extracted_sha256": extracted_hash, "pass": extracted_hash == input_hash}
    result = {
        "started_utc": started, "windows": platform.platform(),
        "machine": platform.machine(), "python": platform.python_version(),
        "input_bytes": input_file.stat().st_size,
        "input_sha256": input_hash, "original_sha256": sha256(original),
        "patched_sha256": sha256(patched),
        "patch_source": "external debugger export" if args.patched else "embedded patch bytes",
        "patched_input": args.patched.name if args.patched else None,
        "tests": rows,
    }
    (lab / "results.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2), flush=True)
    require(all(row["pass"] for row in rows.values()), "At least one experiment check failed.")
    if args.evidence_dir:
        target = args.evidence_dir.resolve()
        (target / "logs").mkdir(parents=True, exist_ok=True)
        shutil.copy2(lab / "results.json", target / "results.json")
        for log in sorted((lab / "logs").glob("*.txt")):
            shutil.copy2(log, target / "logs" / log.name)
        print(f"Copied results.json and logs/ to {target}", flush=True)


if __name__ == "__main__":
    main()

