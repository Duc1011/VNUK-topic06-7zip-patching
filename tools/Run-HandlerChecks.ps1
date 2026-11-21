param(
    [Parameter(Mandatory = $true)][string]$Headless,
    [Parameter(Mandatory = $true)][string]$Original,
    [Parameter(Mandatory = $true)][string]$Patched,
    [Parameter(Mandatory = $true)][string]$WorkDir,
    [Parameter(Mandatory = $true)][string]$OutDir
)
# Runs the x64dbg headless handler checks (-testing -cf + testassert) for four cases.
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
New-Item -ItemType Directory -Force $WorkDir, $OutDir | Out-Null
Set-Content -Encoding ascii (Join-Path $WorkDir 'small.txt') ('VNUK topic 06 handler probe ' * 64)
$template = Get-Content -Raw (Join-Path $repo 'x64dbg-handler-template.txt')
$cases = @(
    @{ Name = 'original-default';  Exe = $Original; Level = 'FFFFFFFF'; Opt = @() },
    @{ Name = 'patched-default';   Exe = $Patched;  Level = '3';        Opt = @() },
    @{ Name = 'patched-explicit5'; Exe = $Patched;  Level = '5';        Opt = @('-mx=5') },
    @{ Name = 'patched-explicit0'; Exe = $Patched;  Level = '0';        Opt = @('-mx=0') }
)
foreach ($c in $cases) {
    $script = Join-Path $WorkDir "$($c.Name).txt"
    Set-Content -Encoding ascii $script $template.Replace('EXPECTED_LEVEL', $c.Level)
    $archive = "$($c.Name).7z"
    Remove-Item -ErrorAction SilentlyContinue (Join-Path $WorkDir $archive)
    $debuggee = @('a', '-t7z', '-mmt=1') + $c.Opt + @($archive, 'small.txt')
    $argList = @('-testing', '-workingDir', "`"$WorkDir`"", '-cf', "`"$script`"", "`"$($c.Exe)`"", '--') + $debuggee
    $log = Join-Path $OutDir "$($c.Name).log"
    $p = Start-Process -FilePath $Headless -ArgumentList $argList -NoNewWindow -PassThru `
        -RedirectStandardOutput $log -RedirectStandardError "$log.err"
    if (-not $p.WaitForExit(120000)) { $p.Kill(); "TIMEOUT $($c.Name)" }
    $err = Get-Content -Raw "$log.err"
    if ($err) { Add-Content $log "`n--- stderr ---`n$err" }
    Remove-Item "$log.err"
    "== $($c.Name): $(Split-Path -Leaf $c.Exe) $($debuggee -join ' ')"
    Select-String -Path $log -Pattern 'HANDLER RVA|x64dbg-test\]' | ForEach-Object { $_.Line }
}
