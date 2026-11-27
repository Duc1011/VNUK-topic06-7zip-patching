#requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Source,
    [Parameter(Mandatory = $true)][string]$Output,
    [string]$BinaryDirectory
)

$ErrorActionPreference = 'Stop'
if (-not $BinaryDirectory) { $BinaryDirectory = Join-Path $PSScriptRoot 'bin' }

function Get-PhysicalDirectory([string]$Path) {
    # Compare actual paths even when a junction or short path aliases the source.
    if (-not ('Topic06.DirectoryPath' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Text;
using Microsoft.Win32.SafeHandles;

namespace Topic06 {
    public static class DirectoryPath {
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern SafeFileHandle CreateFile(string path, uint access, uint share,
            IntPtr security, uint disposition, uint flags, IntPtr template);

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern uint GetFinalPathNameByHandle(SafeFileHandle file, StringBuilder path,
            uint capacity, uint flags);

        public static string Resolve(string path) {
            const uint AllowDirectory = 0x02000000;
            using (var dir = CreateFile(path, 0, 7, IntPtr.Zero, 3, AllowDirectory, IntPtr.Zero)) {
                if (dir.IsInvalid) throw new Win32Exception(Marshal.GetLastWin32Error());
                var buffer = new StringBuilder(32768);
                uint size = GetFinalPathNameByHandle(dir, buffer, (uint)buffer.Capacity, 0);
                if (size == 0) throw new Win32Exception(Marshal.GetLastWin32Error());
                if (size >= buffer.Capacity) throw new InvalidOperationException("Directory path is too long.");
                return buffer.ToString().TrimEnd('\\');
            }
        }
    }
}
'@
    }
    [Topic06.DirectoryPath]::Resolve($Path)
}

function New-CandidateDirectory([string[]]$Parents, [string]$SourceDirectory) {
    $errors = @()
    foreach ($parent in $Parents | Select-Object -Unique) {
        try {
            $physical = Get-PhysicalDirectory $parent
            if ($SourceDirectory) {
                if ($physical.Equals($SourceDirectory, [StringComparison]::OrdinalIgnoreCase) -or
                    $physical.StartsWith($SourceDirectory + '\', [StringComparison]::OrdinalIgnoreCase)) {
                    continue
                }
            }
            $name = 'topic06-compress-' + [Guid]::NewGuid().ToString('N')
            $path = [IO.Directory]::CreateDirectory((Join-Path $parent $name)).FullName
            return [pscustomobject]@{ Path = $path; PhysicalPath = $physical + '\' + $name }
        } catch {
            $errors += $_.Exception.Message
        }
    }
    throw "Cannot create a work directory outside the source. $($errors -join ' ')"
}

function Invoke-7Zip([string]$Executable, [string[]]$ArgumentList) {
    # Capture text and the real native exit code on Windows PowerShell and PowerShell 7.
    $ErrorActionPreference = 'Continue'
    $PSNativeCommandUseErrorActionPreference = $false
    $previousCode = $global:LASTEXITCODE
    $global:LASTEXITCODE = $null
    try {
        $lines = @(& $Executable @ArgumentList 2>&1 | ForEach-Object { $_.ToString() })
        if ($null -eq $global:LASTEXITCODE) { throw "Could not start $Executable. $($lines -join ' ')" }
        [pscustomobject]@{ Code = $global:LASTEXITCODE; Lines = $lines }
    } finally {
        $global:LASTEXITCODE = $previousCode
    }
}

function Confirm-Executable([string]$Path, [string]$Hash) {
    if (-not [IO.File]::Exists($Path)) { throw "Missing $Path. Run setup_compression.py." }
    $hasher = [Security.Cryptography.SHA256]::Create()
    try {
        $stream = [IO.File]::OpenRead($Path)
        try { $actual = [BitConverter]::ToString($hasher.ComputeHash($stream)).Replace('-', '') }
        finally { $stream.Dispose() }
    } finally {
        $hasher.Dispose()
    }
    if ($actual -ne $Hash) {
        throw "Unexpected executable SHA-256 for $Path. Run setup_compression.py with a clean bin directory."
    }
}

$workspace = $null
$workspaceDirectory = $null
$stagingFile = $null
$savedEncoding = [Console]::OutputEncoding
$exitCode = 0
try {
    [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
    if ($env:PROCESSOR_ARCHITECTURE -ne 'AMD64') { throw 'Run in 64-bit PowerShell on Windows x64.' }
    $item = Get-Item -LiteralPath $Source -Force -ErrorAction SilentlyContinue
    if ($null -eq $item -or $item.PSProvider.Name -ne 'FileSystem') {
        throw "Source file or directory does not exist: $Source"
    }
    $provider = $null
    $drive = $null
    $destination = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Output, [ref]$provider, [ref]$drive)
    $fileName = [IO.Path]::GetFileName($destination)
    if ($provider.Name -ne 'FileSystem' -or [IO.Path]::GetExtension($destination) -ne '.7z' -or
        $fileName.IndexOfAny([IO.Path]::GetInvalidFileNameChars()) -ge 0 -or
        $fileName -match '^(CON|PRN|AUX|NUL|COM[1-9\u00b9\u00b2\u00b3]|LPT[1-9\u00b9\u00b2\u00b3])\.') {
        throw 'Output must be a valid filesystem path ending in .7z.'
    }
    $destParent = [IO.Path]::GetDirectoryName($destination)
    if (-not [IO.Directory]::Exists($destParent)) { throw "Output directory does not exist: $destParent" }
    if (Test-Path -LiteralPath $destination) { throw "Output already exists: $destination" }

    $bin = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($BinaryDirectory)
    $original = Join-Path $bin '7za.exe'
    $patched = Join-Path $bin '7za-ppmd.exe'
    Confirm-Executable $original 'dd3757f31c97e33776f2590317d4fb12f2da075db3dbb1e3f94d0f2a01d84ffa'
    $candidates = @(
        @{ Name = 'Original default'; Exe = $original; Switches = @() }
        @{ Name = 'Patched default'; Exe = $patched; Switches = @() }
        @{ Name = 'PPMd Ultra'; Exe = $original; Switches = @('-m0=PPMd', '-mx=9') }
    )

    $sourceDirectory = $null
    $sourceParent = $item.DirectoryName
    $entry = '.\' + $item.Name
    $workParents = @($destParent, [IO.Path]::GetTempPath())
    if ($item.PSIsContainer) {
        $sourceDirectory = Get-PhysicalDirectory $item.FullName
        if ($item.Parent) {
            $sourceParent = $item.Parent.FullName
            $workParents += $sourceParent
        } else {
            $sourceParent = $item.FullName
            $entry = '.'
        }
    }
    $workspaceDirectory = New-CandidateDirectory $workParents $sourceDirectory
    $workspace = $workspaceDirectory.Path
    $table = @()
    Push-Location -LiteralPath $sourceParent
    try {
        for ($index = 0; $index -lt $candidates.Count; $index++) {
            $candidate = $candidates[$index]
            $path = Join-Path $workspace ('candidate-{0}.7z' -f ($index + 1))
            $row = [pscustomobject]@{ Candidate = $candidate.Name; Method = '-'; Bytes = $null;
                Check = 'FAILED'; Rank = $index; Path = $path }
            $table += $row
            Write-Host "Trying $($candidate.Name)..."
            try {
                if ($candidate.Exe -eq $patched) {
                    Confirm-Executable $patched '1cb1b0b4546dc11598a2ea3a22a639e475c2d33b8f7b8a94e304a3a18faa6b19'
                }
                $create = Invoke-7Zip $candidate.Exe (@('a', '-sccUTF-8', '-t7z', '-mmt=1', '-spd', '-snl',
                    "-w$workspace") + $candidate.Switches + @('--', $path, $entry))
                if ($create.Code -ne 0 -or -not [IO.File]::Exists($path)) {
                    $row.Check = "Create failed ($($create.Code))"
                    throw ($create.Lines | Select-Object -Last 8 | Out-String).Trim()
                }
                $row.Bytes = ([IO.FileInfo]::new($path)).Length
                $tested = Invoke-7Zip $original @('t', '-sccUTF-8', '--', $path)
                if ($tested.Code -ne 0) {
                    $row.Check = "Test failed ($($tested.Code))"
                    throw ($tested.Lines | Select-Object -Last 8 | Out-String).Trim()
                }
                $list = Invoke-7Zip $original @('l', '-sccUTF-8', '-slt', '--', $path)
                if ($list.Code -ne 0) {
                    $row.Check = "List failed ($($list.Code))"
                    throw ($list.Lines | Select-Object -Last 8 | Out-String).Trim()
                }
                $method = $list.Lines | Where-Object { $_ -match '^Method =' } | Select-Object -First 1
                $row.Method = if ($method -and $method.Substring(8).Trim()) { $method.Substring(8).Trim() } else { '(empty)' }
                $row.Check = 'PASS'
            } catch {
                Write-Warning "$($candidate.Name): $($_.Exception.Message)"
            }
        }
    } finally {
        Pop-Location
    }

    $table | Format-Table Candidate, Method, Bytes, Check -AutoSize | Out-Host
    $winner = $table | Where-Object Check -eq 'PASS' | Sort-Object Bytes, Rank | Select-Object -First 1
    if ($null -eq $winner) { throw 'No valid archive. All candidates failed compression or verification.' }

    # Publish only after validation. The final rename is on the destination volume and never overwrites.
    $stagePath = Join-Path $destParent ('.topic06-' + [Guid]::NewGuid().ToString('N') + '.tmp')
    $writer = [IO.File]::Open($stagePath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
    $stagingFile = $stagePath
    try {
        $reader = [IO.File]::OpenRead($winner.Path)
        try { $reader.CopyTo($writer) } finally { $reader.Dispose() }
    } finally {
        $writer.Dispose()
    }
    try {
        [IO.File]::Move($stagingFile, $destination)
    } catch [IO.IOException] {
        if (Test-Path -LiteralPath $destination) { throw "Output already exists: $destination" }
        throw
    }
    $stagingFile = $null

    $tie = @($table | Where-Object { $_.Check -eq 'PASS' -and $_.Bytes -eq $winner.Bytes }).Count -gt 1
    $reason = if ($tie) { 'tie resolved in candidate order' } else { 'lowest measured byte count' }
    Write-Host "Selected $($winner.Candidate) ($($winner.Bytes) bytes): smallest of the successful candidates ($reason)."
    if ($table[0].Check -eq 'PASS') {
        $saved = $table[0].Bytes - $winner.Bytes
        $fraction = 100.0 * $saved / $table[0].Bytes
        Write-Host ('Reduction vs. original default: {0} bytes ({1:F2}%).' -f $saved, $fraction)
    }
    Write-Host "Archive: $destination"
} catch {
    [Console]::Error.WriteLine("Error: $($_.Exception.Message)")
    $exitCode = 1
} finally {
    [Console]::OutputEncoding = $savedEncoding
    try {
        if ($stagingFile) { [IO.File]::Delete($stagingFile) }
    } catch {
        [Console]::Error.WriteLine("Could not remove staging file $stagingFile. $($_.Exception.Message)")
        $exitCode = 1
    }
    try {
        if ($workspace -and [IO.Directory]::Exists($workspace)) {
            if ((Get-PhysicalDirectory $workspace) -ne $workspaceDirectory.PhysicalPath) {
                throw 'The work directory now resolves to a different path.'
            }
            [IO.Directory]::Delete($workspace, $true)
        }
    } catch {
        [Console]::Error.WriteLine("Could not remove work directory $workspace. $($_.Exception.Message)")
        $exitCode = 1
    }
}
exit $exitCode
