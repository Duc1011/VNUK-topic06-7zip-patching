# Thí nghiệm Fast (3) ban đầu

This experiment modifies the default `.7z` compression level in the official
**7-Zip Extra 26.06 x64** standalone executable (`x64/7za.exe`) from **Normal (`-mx=5`)**
to **Fast (`-mx=3`)**, while keeping explicit `-mx` command-line overrides working.

Run the demo commands from `legacy-fast3/` inside the repository. The [project README](../README.md)
covers the PPMd compression tool. The original Fast (3) artifacts are under `evidence/`, including
the [later regression run](evidence/regression/). Local generated runs are saved as `topic06-*`
directories here by default.

## Patch Summary

- **Target binary:** `x64/7za.exe` from `7z2606-extra.7z` (7-Zip 26.06 x64)
  - Package SHA-256: `396c180f12d2247c24b0b1fcd482c6fc2a2700f61211ffede1061dd971f5e104`
  - Original `7za.exe` SHA-256: `dd3757f31c97e33776f2590317d4fb12f2da075db3dbb1e3f94d0f2a01d84ffa`
  - Patched `7za-patched.exe` SHA-256: `985d511efd476fe87d7258e61abb3e99a03e7f63915203550bd28a46aae53b98`
- **Technique:** **in-place instruction replacement with NOP padding**
- **Location:** inside initializer `FUN_004777a0` (Ghidra `0x004777a0`–`0x00477837`, 152 bytes)
  - Virtual Address (default image base `0x00400000`): `0x004777C8`
  - RVA: `0x777C8` (`.text`)
  - File offset: `0x76BC8`
  - Patch window: **24 bytes** (`0x76BC8`–`0x76BDF`), **17 bytes** actually modified

Because `xor edx, edx` at RVA `0x777A0` guarantees `edx == 0`, four consecutive 6-byte
byte-stores (`mov byte ptr [rcx+0x9A..0x9D], dl`) are consolidated into one 6-byte
dword-store (`mov dword ptr [rcx+0x9A], edx`), freeing 18 bytes in place for
`mov dword ptr [rcx+0x28], 3` (7 bytes) plus 11 `nop` (`0x90`) bytes:

```text
Before (24 bytes at RVA 0x777C8 / file offset 0x76BC8):
  777C8  88 91 9A 00 00 00     mov byte ptr [rcx+0x9A], dl
  777CE  88 91 9B 00 00 00     mov byte ptr [rcx+0x9B], dl
  777D4  88 91 9C 00 00 00     mov byte ptr [rcx+0x9C], dl
  777DA  88 91 9D 00 00 00     mov byte ptr [rcx+0x9D], dl

After (in-place instruction replacement with NOP padding):
  777C8  89 91 9A 00 00 00     mov dword ptr [rcx+0x9A], edx
  777CE  C7 41 28 03 00 00 00  mov dword ptr [rcx+0x28], 3
  777D5  90 .. 90 (11 bytes)   nop (x11)
```

---

## Demo 1: Automated Reproduction (PowerShell + Python)

Requires **Windows x64** and **Python 3.11+**. Allow ~230 MiB of free disk space for
the generated 64 MiB fixture, `.7z` archives, and extracted output.

### 1. Run all 7 test cases (`T01`–`T07`)

```powershell
python .\reproduce.py
```

`reproduce.py` downloads `7z2606-extra.7z`, checks its SHA-256, extracts `x64/7za.exe`
with Windows `tar`, verifies the original hash and 24-byte window, writes
`7za-patched.exe`, and runs `T01`–`T07` in a new `topic06-*` directory.

Useful options:
- Offline run: `--package C:\path\to\7z2606-extra.7z` or `--original C:\path\to\7za.exe`
- Test an externally patched binary (e.g. from x64dbg): `--patched C:\path\to\7za-patched.exe`
- Parallel archive creation (`-mmt=1` is still enforced per process): `--jobs 3`
- Save refreshed `results.json` and `logs/` into `evidence/`: `--evidence-dir evidence`

### 2. Verify the patch and `topic06.1337` byte-for-byte

```powershell
python .\verify_patch.py --original C:\path\to\7za.exe --report evidence\patch-verification.txt
```

This checks the original SHA-256, applies `topic06.1337` to a copy, confirms byte-for-byte
equality with `reproduce.py`, and verifies that all 17 modified bytes lie inside
`0x76BC8`–`0x76BDF`. Pass `--candidate C:\path\to\7za-patched.exe` to check an EXE
exported by x64dbg GUI.

### 3. Cross-check SHA-256 hashes with PowerShell `Get-FileHash`

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\Get-Topic06Hashes.ps1 `
    -Lab .\topic06-<id> `
    -Original C:\path\to\7za.exe `
    -Patched C:\path\to\7za-patched.exe `
    -OutFile evidence\hashes-powershell.txt
```

Pass criteria verified by both `reproduce.py` and `Get-FileHash -Algorithm SHA256`:
- `T01` (original, no `-mx`) == `T03` (original, `-mx=5`, `LZMA2:25`)
- `T04` (patched, no `-mx`) == `T02` (original, `-mx=3`, `LZMA2:22`)
- `T05` (patched, `-mx=5`) == `T03` (original, `-mx=5`, `LZMA2:25`)
- `T06` (patched, `-mx=0`) uses method `Copy`
- `T07` (`t` + `x` on `T04.7z` using original `7za.exe`) restores exact `input.txt` SHA-256

---

## Demo 2: Manual Demonstration in x64dbg (GUI)

Use **x64dbg `2026.05.27`** (`release\x64\x64dbg.exe`).

### A. Manual in-place assembly edit (recommended for live demo)

1. Extract `x64/7za.exe` from `7z2606-extra.7z`, open it in `x64dbg.exe`, and leave it paused.
2. Jump to `7za.exe:$777C8` (press `Ctrl+G` in the CPU view, or run `disasm 7za.exe:$777C8` in the bottom Command bar).
3. Capture a **before** screenshot showing the four `mov byte ptr [rcx+0x9A..0x9D], dl` instructions.
4. Press `Space` on `7za.exe:$777C8` and assemble:
   - `mov dword ptr [rcx+0x9A], edx`
5. Press `Space` on `7za.exe:$777CE` and assemble:
   - `mov dword ptr [rcx+0x28], 3`
6. Right-click `7za.exe:$777D5` → **Follow in Dump → Selected Address**, select the remaining
   11 bytes (`91 9C 00 00 00 88 91 9D 00 00 00`) in **Dump 1**, choose **Binary → Fill...**,
   and enter the hex value `90`. *(Do not use the `fill` console command before
   `File → Patch file`, because `fill` writes memory without registering entries in x64dbg's
   Patch table.)*
7. Jump back to `7za.exe:$777C8` (`disasm 7za.exe:$777C8`) and capture an **after** screenshot
   showing the two `mov` instructions followed by 11 `nop`s (all 17 modified bytes highlighted in red).
8. Open **File → Patch file** (`Ctrl+P`), confirm 17 byte patches in `7za.exe`, click
   **Patch File**, and save as `7za-patched.exe`.
9. Verify the exported binary's SHA-256 and run `T01`–`T07` with it:

```powershell
Get-FileHash -Algorithm SHA256 C:\path\to\7za-patched.exe
python .\reproduce.py --original C:\path\to\7za.exe --patched C:\path\to\7za-patched.exe --jobs 3
```

### B. Quick import using `topic06.1337`

For a fast demo reset, open `7za.exe` in `x64dbg.exe`, open **File → Patch file** (`Ctrl+P`),
click **Import**, select `topic06.1337`, inspect `7za.exe:$777C8` in the CPU view, and click
**Patch File** to save `7za-patched.exe`.

> **GUI verification:** Completed on Windows 11 x64 with `x64dbg.exe` (`May 27 2026`).
> Captured screenshots are stored in `evidence/x64dbg-before.jpg`, `evidence/x64dbg-after.jpg`,
> and `evidence/x64dbg-patches.png`. The binary exported via **File → Patch file**
> (`7za-patched-gui.exe`) matched SHA-256
> `985d511efd476fe87d7258e61abb3e99a03e7f63915203550bd28a46aae53b98` and passed all
> `verify_patch.py`, `reproduce.py --patched`, and `Get-FileHash` checks.

---

## Headless x64dbg Verification (`2026.05.27`)

All automated debugger checks were executed with **x64dbg headless `2026.05.27`**
(`snapshot_2026-05-27_12-11.zip`, `release\x64\headless.exe`) using `-testing`, `-cf`,
and `testassert`.

### 1. Assemble and export the 24-byte patch

Replace `EXPORT_PATH` in `x64dbg-apply-template.txt` with an absolute writable path (for
example `C:\work\x64dbg-export.bin`) and run:

```powershell
& C:\path\to\x64dbg\release\x64\headless.exe -testing -cf C:\work\x64dbg-apply.txt C:\path\to\7za.exe
```

`x64dbg-apply-template.txt` assembles both `mov` instructions, fills 11 `0x90` bytes,
asserts `testassert ReadByte(mod.main()+777D1)==3`, and exports 24 bytes via `savedata`.
Expected final line: `[x64dbg-test] FINAL status=pass asserts=1`.

### 2. Verify runtime compression level at handler breakpoint (`RVA 0x783E9`)

`x64dbg-handler-template.txt` sets a breakpoint at `mod.main()+783E9` (`CALL 0x00463fb4`
inside `FUN_0047829c`) and asserts both the stopped RVA and `[rcx+0x28]` (`CMultiMethodProps`
level) via `testassert`. Run all four runtime cases (`original-default`, `patched-default`,
`patched-explicit5`, `patched-explicit0`) with:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\Run-HandlerChecks.ps1 `
    -Headless C:\path\to\x64dbg\release\x64\headless.exe `
    -Original C:\path\to\7za.exe `
    -Patched C:\path\to\7za-patched.exe `
    -WorkDir C:\work\handler `
    -OutDir C:\work\handler-logs
```

Observed levels at `RVA 0x783E9`:
- `original-default`: `LEVEL=FFFFFFFF` (`pass asserts=2`)
- `patched-default`: `LEVEL=3` (`pass asserts=2`)
- `patched-explicit5` (`-mx=5`): `LEVEL=5` (`pass asserts=2`)
- `patched-explicit0` (`-mx=0`): `LEVEL=0` (`pass asserts=2`)

---

## Static Analysis in Ghidra & `objdump` Cross-Check

The original `x64/7za.exe` was analyzed with **Ghidra 12.2 PUBLIC** (`build 2026-Oct-16 1220 UTC`,
`analyzeHeadless` + `tools/Topic06Ghidra.java`) and cross-checked against
**GNU objdump 2.44** (`MinGW-W64 x86_64`):

```cmd
analyzeHeadless.bat <project_dir> Topic06 -import C:\path\to\7za.exe -overwrite ^
    -scriptPath .\tools -postScript Topic06Ghidra.java evidence\ghidra-analysis.txt
```

- Patch site `0x004777C8` (RVA `0x777C8`, file offset `0x76BC8`) lies in `FUN_004777a0`
  (`0x004777a0`–`0x00477837`, 152 bytes), called from `FUN_00476f94` (`0x00477016`) and
  `FUN_0047a184` (`0x0047a1be`).
- Every instruction address and machine-code byte in `FUN_004777a0` matches `objdump -d -M intel`
  exactly.

---

## Evidence Files

- `evidence/patch-verification.txt` — Step 1 verification report (`verify_patch.py`): original SHA-256, `.1337` vs `reproduce.py` vs `x64dbg` export byte-for-byte comparison, and full 24-byte diff table.
- `evidence/ghidra-analysis.txt` — Step 2 Ghidra 12.2 PUBLIC disassembly, callers, and decompiler output for `FUN_004777a0` and `RVA 0x783E9`, cross-checked against `GNU objdump 2.44`.
- `evidence/debugger.txt` — Step 3 & 5 `x64dbg 2026.05.27` headless assembly/export, runtime `testassert` results, and verified GUI `File → Patch file` export summary.
- `evidence/x64dbg-before.jpg`, `evidence/x64dbg-after.jpg`, `evidence/x64dbg-patches.png` — Step 3 x64dbg GUI screenshots (before patch, after patch with 17 red bytes, and 17-entry Patches dialog).
- `evidence/results.json` — Step 4 machine-readable results for `T01`–`T07` on Windows 11 x64 (`Python 3.14.0`).
- `evidence/logs/` — Step 4 per-command stdout/stderr and exit codes for `T01`–`T07`.
- `evidence/hashes-powershell.txt` — Step 4 independent PowerShell `Get-FileHash -Algorithm SHA256` cross-check.
- `topic06.1337` — Module-relative x64dbg patch file (17 changed bytes).
- `x64dbg-apply-template.txt` / `x64dbg-handler-template.txt` — Headless x64dbg scripts for `-testing -cf` + `testassert`.

## References

- Official 7-Zip 26.06 release and checksums: https://github.com/ip7z/7zip/releases/expanded_assets/26.06
- x64dbg `2026.05.27` release: https://github.com/x64dbg/x64dbg/releases/tag/2026.05.27
- Ghidra `12.2 PUBLIC` release: https://github.com/NationalSecurityAgency/ghidra/releases/tag/Ghidra_12.2_build
