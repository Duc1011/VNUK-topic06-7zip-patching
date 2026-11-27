"""Benchmark verified 7-Zip 26.06 x64 configurations and verify extracted bytes."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import random
import re
import shutil
import subprocess
import tempfile
import time
import zipfile

from topic06_common import PACKAGE_SHA, ORIGINAL_SHA, generate_input, obtain_original, require, sha256


CONFIGS = {
    "original-default": [],
    "lzma2-5": ["-m0=LZMA2", "-mx=5"],
    "lzma2-9": ["-m0=LZMA2", "-mx=9"],
    "ppmd-5": ["-m0=PPMd", "-mx=5"],
    "ppmd-9": ["-m0=PPMd", "-mx=9"],
}


def manifest(source):
    paths = [source, *source.rglob("*")] if source.is_dir() else [source]
    return {path.relative_to(source.parent).as_posix(): None if path.is_dir() else sha256(path)
            for path in sorted(paths)}


def build_fixtures(lab, existing_fixture=None):
    fixture = lab / "input.txt"
    if existing_fixture:
        shutil.copyfile(existing_fixture, fixture)
    else:
        generate_input(fixture)
    require(fixture.stat().st_size == 64 * 1024**2 and sha256(fixture) ==
            "a5cfb3581a8ac9d67cb26ae3b3140fe09bb7ec80338a7b6e97fe5d67d004866c",
            "The 64 MiB input differs from the Fast (3) experiment fixture.")
    tree = lab / "Tài liệu dự án"
    (tree / "Nhật ký").mkdir(parents=True)
    (tree / "Ghi chú").mkdir()
    (tree / "Thư mục rỗng").mkdir()
    rng = random.Random(260607)
    messages = ["Request served from cache", "Queued invoice generation", "Worker heartbeat received",
                "Uploaded source document", "Finished SHA-256 integrity check", "Scheduled weekly report",
                "Retrying transient resource failure", "Saved archive to storage", "Synchronized member profile"]
    for day in range(1, 13):
        log = tree / "Nhật ký" / f"Ngày {day:02d}.log"
        with log.open("w", encoding="utf-8", newline="\n") as stream:
            for second in range(6000):
                message = rng.choice(messages)
                stream.write(f"2026-11-{day:02d}T{second//3600:02d}:{second//60%60:02d}:{second%60:02d}Z "
                             f"{rng.choice(['INFO', 'INFO', 'DEBUG', 'WARN'])} "
                             f"worker={rng.randrange(32):02d} user={rng.randrange(500):03d} "
                             f"duration_ms={rng.randrange(1500):04d} {message}\n")
        (tree / "Ghi chú" / f"Báo cáo {day:02d}.txt").write_text(
            f"Tổng hợp hoạt động ngày {day:02d}\n" +
            "Tạo bản lưu trữ cho tài liệu dự án và đối chiếu mã băm sau khi giải nén.\n"
            "Nhật ký ghi thời gian xử lý và trạng thái của các tiến trình.\n" * 100,
            encoding="utf-8", newline="\n")
    # A ZIP with an already-deflated, deterministic high-entropy member.
    packed = lab / "Đã nén.zip"
    payload = random.Random(260608).randbytes(2 * 1024**2)
    with zipfile.ZipFile(packed, "w") as archive:
        archive.writestr(zipfile.ZipInfo("sensor-capture.bin", (2024, 1, 1, 0, 0, 0)), payload,
                         compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    for path in [fixture, packed, *tree.rglob("*"), tree]:
        os.utime(path, (1700000000, 1700000000))
    return {"fixture64": fixture, "text-logs": tree, "compressed-zip": packed}


def run_command(command, cwd, log):
    start = time.perf_counter()
    result = subprocess.run(list(map(str, command)), cwd=cwd, capture_output=True,
                            encoding="utf-8", errors="replace")
    elapsed = round(time.perf_counter() - start, 4)
    log.write_text(subprocess.list2cmdline(list(map(str, command))) +
                   f"\nExit code: {result.returncode}\nElapsed seconds: {elapsed}\n\n" +
                   result.stdout + result.stderr, encoding="utf-8")
    return result, elapsed


def measure(lab, logs, original, source, case, executable, options, expected):
    archive = lab / "candidate.7z"
    require(not archive.exists(), f"Archive already exists for {case}.")
    result, elapsed = run_command(
        [executable, "a", "-sccUTF-8", "-t7z", "-mmt=1", *options, "--", archive, source.name],
        source.parent, logs / f"{case}-create.txt")
    row = {"options": options, "create_exit_code": result.returncode, "seconds": elapsed}
    if result.returncode != 0 or not archive.is_file():
        row["verified"] = False
        archive.unlink(missing_ok=True)
        return row
    row.update(archive_bytes=archive.stat().st_size, archive_sha256=sha256(archive))
    listing, _ = run_command([original, "l", "-sccUTF-8", "-slt", archive], lab, logs / f"{case}-list.txt")
    check, _ = run_command([original, "t", "-sccUTF-8", archive], lab, logs / f"{case}-test.txt")
    with tempfile.TemporaryDirectory(prefix="extract-", dir=lab) as extracted_dir:
        extracted = Path(extracted_dir)
        extraction, _ = run_command([original, "x", "-sccUTF-8", archive, f"-o{extracted}"],
                                    lab, logs / f"{case}-extract.txt")
        restored = extracted / source.name
        actual = manifest(restored) if restored.exists() else {}
        hashes_match = actual == expected and sorted(p.name for p in extracted.iterdir()) == [source.name]
        (logs / f"{case}-manifest.json").write_text(
            json.dumps({"matches": hashes_match, "extracted": actual}, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8")
    method = re.search(r"^Method = (.+)$", listing.stdout, re.MULTILINE)
    row.update(method=method[1].strip() if method else None, list_exit_code=listing.returncode,
               test_exit_code=check.returncode, extract_exit_code=extraction.returncode,
               paths_and_sha256_match=hashes_match,
               verified=bool(method and hashes_match and listing.returncode == check.returncode == extraction.returncode == 0))
    archive.unlink()
    return row


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, help="Use a local official 7z2606-extra.7z package.")
    parser.add_argument("--fixture", type=Path, help="Reuse input.txt from the original experiment.")
    parser.add_argument("--evidence-dir", type=Path, required=True)
    args = parser.parse_args()
    require(os.name == "nt" and platform.machine().upper() in {"AMD64", "X86_64"}, "Run on Windows x64.")
    evidence = args.evidence_dir.resolve()
    evidence.mkdir(parents=True)
    logs = evidence / "logs"
    logs.mkdir()
    run = {"started_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "windows": platform.platform(), "machine": platform.machine(), "python": platform.python_version(),
           "threads": 1, "format": "7z", "datasets": {}}
    with tempfile.TemporaryDirectory(prefix="topic06-bench-", dir=Path.cwd()) as work_dir:
        lab = Path(work_dir)
        package = args.package.resolve() if args.package else None
        original = obtain_original(lab, package)
        require(sha256(original) == ORIGINAL_SHA, "Unexpected original executable SHA-256.")
        run.update(package_sha256=sha256(package or lab / "7z2606-extra.7z"), original_sha256=sha256(original))
        require(run["package_sha256"] == PACKAGE_SHA, "Unexpected package SHA-256.")
        for dataset, source in build_fixtures(lab, args.fixture).items():
            expected = manifest(source)
            cases = {}
            run["datasets"][dataset] = {"source_manifest": expected,
                                         "input_bytes": sum(p.stat().st_size for p in
                                                            (source.rglob("*") if source.is_dir() else [source])
                                                            if p.is_file()), "cases": cases}
            for name, switches in CONFIGS.items():
                cases[name] = measure(lab, logs, original, source, f"{dataset}-{name}", original, switches, expected)
                print(dataset, name, cases[name], flush=True)
                write_json(evidence / "results.json", run)
    require(all(case["verified"] for data in run["datasets"].values() for case in data["cases"].values()),
            "At least one benchmark case did not verify. Check the saved logs.")


if __name__ == "__main__":
    main()
