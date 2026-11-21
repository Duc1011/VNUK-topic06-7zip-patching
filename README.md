# VNUK Topic 06 experiment kit

This experiment changes the default level for new .7z archives in the verified
7-Zip Extra 26.06 x64 executable. All seven cases in the published results ran
on Windows 11 x64 using a generated 64 MiB text fixture.

## Reproduce from PowerShell

Unzip the kit, open PowerShell in the extracted folder, and run with Python
3.11 or newer:

    python .\reproduce.py

The script downloads the official Extra package, checks its published SHA-256,
extracts x64/7za.exe with Windows tar, and validates the executable hash and
original bytes. It writes the patched EXE and runs T01-T07 inside a new
topic06-* directory. The script prints that directory and writes results.json
and per-command logs. Allow roughly 230 MiB for input, archives and extraction.

For an offline run, supply the official archive with --package or its
x64/7za.exe with --original. --jobs 3 runs independent archive creation cases
concurrently. Each 7-Zip process still uses -mmt=1.

## Demonstrate the edit in x64dbg

1. Extract x64/7za.exe from the official Extra package. Open that original EXE
   in x64dbg and leave it paused.
2. Open File > Patch file, choose Import, then select topic06.1337. The patch
   is pinned to the executable hash in evidence/results.json.
3. In the CPU view, go to 7za.exe:$777C8 and inspect the two MOV instructions.
   The first consolidates four zero stores. The second sets the level to 3.
4. In the patch dialog choose Patch File and save a new file as
   7za-patched.exe. Check it with the following command:

       python .\reproduce.py --original "C:\path\to\7za.exe" --patched "C:\path\to\7za-patched.exe"

5. Compare T04 with T02, compare T05 with T03, and finish by showing the
   extraction SHA-256 check from T07.

The measured run used x64dbg headless to assemble and export the patch bytes.
The Python runner also supports writing those exact bytes directly. The kit
includes the debugger command template used to export the bytes. Substitute
an absolute writable path for EXPORT_PATH to use it with the -testing -cf
arguments to x64dbg's headless.exe.

## Evidence

- results.json records the executable and archive hashes, observed methods,
  byte counts, and test results.
- logs/ records the actual 7-Zip commands and their stdout, stderr and exit codes.
- debugger.txt records the patch location, disassembly and handler levels.
- topic06.1337 contains the changed bytes as module-relative x64dbg entries.

Official release and published checksums:
https://github.com/ip7z/7zip/releases/expanded_assets/26.06

x64dbg used for this experiment:
https://github.com/x64dbg/x64dbg/releases/tag/2026.05.27

