param(
    [Parameter(Mandatory = $true)][string]$Lab,
    [Parameter(Mandatory = $true)][string]$Original,
    [string[]]$Patched = @(),
    [string]$OutFile
)
# Independent PowerShell cross-check of reproduce.py results using Get-FileHash -Algorithm SHA256.
$ErrorActionPreference = 'Stop'
$lines = New-Object System.Collections.Generic.List[string]
function Say([string]$text) { $lines.Add($text); Write-Output $text }
function Get-Sha([string]$path) { (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash }
$fail = 0
function Check([bool]$ok, [string]$text) {
    if (-not $ok) { $script:fail++ }
    Say ("[{0}] {1}" -f ($(if ($ok) { 'PASS' } else { 'FAIL' })), $text)
}

Say "Get-FileHash -Algorithm SHA256 cross-check"
Say ("PowerShell {0}; {1}; {2}" -f $PSVersionTable.PSVersion, [Environment]::OSVersion.VersionString, $env:PROCESSOR_ARCHITECTURE)
Say ("Lab folder: {0}" -f (Split-Path -Leaf $Lab))
Say ""
$officialOriginal = 'DD3757F31C97E33776F2590317D4FB12F2DA075DB3DBB1E3F94D0F2A01D84FFA'
$officialPatched  = '985D511EFD476FE87D7258E61ABB3E99A03E7F63915203550BD28A46AAE53B98'
$orig = Get-Sha $Original
Say ("{0}  {1}" -f $orig, 'original 7za.exe')
Check ($orig -eq $officialOriginal) 'Original EXE matches the official 26.06 x64 7za.exe hash'
$labPatched = Join-Path $Lab '7za-patched.exe'
foreach ($p in @($Patched + $labPatched)) {
    $h = Get-Sha $p
    Say ("{0}  {1}" -f $h, (Split-Path -Leaf $p))
    Check ($h -eq $officialPatched) ("{0} matches the expected patched hash" -f (Split-Path -Leaf $p))
}
Say ""
$hashes = @{}
foreach ($name in 'input.txt', 'T01.7z', 'T02.7z', 'T03.7z', 'T04.7z', 'T05.7z', 'T06.7z', 'extracted\input.txt') {
    $path = Join-Path $Lab $name
    $hashes[$name] = Get-Sha $path
    Say ("{0}  {1,12}  {2}" -f $hashes[$name], (Get-Item -LiteralPath $path).Length, $name)
}
Say ""
Check ($hashes['T01.7z'] -eq $hashes['T03.7z']) 'T01 (original, no -mx) == T03 (original, -mx=5)'
Check ($hashes['T04.7z'] -eq $hashes['T02.7z']) 'T04 (patched, no -mx) == T02 (original, -mx=3)'
Check ($hashes['T05.7z'] -eq $hashes['T03.7z']) 'T05 (patched, -mx=5) == T03 (original, -mx=5)'
Check ($hashes['T02.7z'] -ne $hashes['T03.7z']) 'T02 (Fast) differs from T03 (Normal)'
$t06 = Select-String -LiteralPath (Join-Path $Lab 'logs\T06-list.txt') -Pattern '^Method = (.+)$' | Select-Object -First 1
$method = if ($t06) { $t06.Matches[0].Groups[1].Value.Trim() } else { '<missing>' }
Check ($method -eq 'Copy') ("T06 (patched, -mx=0) method = {0}" -f $method)
Check ($hashes['extracted\input.txt'] -eq $hashes['input.txt']) 'T07 extracted\input.txt == input.txt'
Say ""
Say ("RESULT: {0}" -f ($(if ($fail -eq 0) { 'PASS' } else { "FAIL ($fail)" })))
if ($OutFile) { $lines | Set-Content -Encoding utf8 $OutFile }
exit $fail
