param(
    [Parameter(Mandatory = $true)][string]$Headless,
    [Parameter(Mandatory = $true)][string]$Original,
    [Parameter(Mandatory = $true)][string]$Patched,
    [Parameter(Mandatory = $true)][string]$WorkDir,
    [Parameter(Mandatory = $true)][string]$OutDir,
    [ValidateRange(1, [int]::MaxValue)][int]$TimeoutMs = 120000
)
# Runs the x64dbg headless handler checks (-testing -cf + testassert) for four cases.
# Exits 0 only when all four cases finish before TimeoutMs with exit code 0 and
# log "[x64dbg-test] FINAL status=pass asserts=2".
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

$passedCases = 0
$failedCases = New-Object System.Collections.Generic.List[string]

foreach ($c in $cases) {
    $script = Join-Path $WorkDir "$($c.Name).txt"
    Set-Content -Encoding ascii $script $template.Replace('EXPECTED_LEVEL', $c.Level)
    $archive = "$($c.Name).7z"
    Remove-Item -ErrorAction SilentlyContinue (Join-Path $WorkDir $archive)
    $debuggee = @('a', '-t7z', '-mmt=1') + $c.Opt + @($archive, 'small.txt')
    $argList = @('-testing', '-workingDir', "`"$WorkDir`"", '-cf', "`"$script`"", "`"$($c.Exe)`"", '--') + $debuggee
    $log = Join-Path $OutDir "$($c.Name).log"
    $errLog = "$log.err"
    Remove-Item -ErrorAction SilentlyContinue $log, $errLog

    "== $($c.Name): $(Split-Path -Leaf $c.Exe) $($debuggee -join ' ')"

    $reasons = New-Object System.Collections.Generic.List[string]
    $timedOut = $false
    $exitCode = $null

    try {
        $p = Start-Process -FilePath $Headless -ArgumentList $argList -NoNewWindow -PassThru `
            -RedirectStandardOutput $log -RedirectStandardError $errLog
        # Cache the Win32 handle immediately so Windows PowerShell 5.1 always populates ExitCode.
        $null = $p.Handle

        if (-not $p.WaitForExit($TimeoutMs)) {
            $timedOut = $true
            $reasons.Add("timed out after ${TimeoutMs}ms (debugger PID $($p.Id) terminated)")
            $prevPref = $ErrorActionPreference
            $ErrorActionPreference = 'Continue'
            try {
                & taskkill.exe /PID $p.Id /T /F 2>&1 | Out-Null
            } finally {
                $ErrorActionPreference = $prevPref
            }
            if (-not $p.HasExited) {
                try { $p.Kill() } catch {}
            }
            try { $null = $p.WaitForExit(5000) } catch {}
        } else {
            # Flush redirected output buffers and refresh exit code.
            $p.WaitForExit()
            $exitCode = $p.ExitCode
            if ($null -eq $exitCode) {
                $reasons.Add('debugger exit code was unavailable')
            } elseif ($exitCode -ne 0) {
                $reasons.Add("debugger exited with non-zero code $exitCode")
            }
        }
    } catch {
        $reasons.Add("failed to run debugger: $($_.Exception.Message)")
    }

    if (Test-Path -LiteralPath $errLog) {
        $err = Get-Content -Raw -LiteralPath $errLog -ErrorAction SilentlyContinue
        if ($err) { Add-Content -LiteralPath $log "`n--- stderr ---`n$err" }
        Remove-Item -LiteralPath $errLog -ErrorAction SilentlyContinue
    }
    if ($timedOut) {
        Add-Content -LiteralPath $log "`n[Run-HandlerChecks] ERROR: $($c.Name) timed out after ${TimeoutMs}ms; debugger process terminated."
    }

    $logLines = if (Test-Path -LiteralPath $log) {
        @(Get-Content -LiteralPath $log -ErrorAction SilentlyContinue)
    } else {
        @()
    }

    $logLines | Where-Object { $_ -match 'HANDLER RVA|x64dbg-test\]' } | ForEach-Object { $_ }

    $finalLines  = @($logLines | Where-Object { $_ -match '^\[x64dbg-test\]\s+FINAL\b' })
    $assertFails = @($logLines | Where-Object { $_ -match '^\[x64dbg-test\]\s+ASSERT FAIL\b' })
    $hasPass     = [bool]($finalLines | Where-Object { $_ -match '^\[x64dbg-test\]\s+FINAL\s+status=pass\s+asserts=2(\s|$)' })
    $hasFail     = [bool]($finalLines | Where-Object { $_ -match '\bstatus=fail\b' }) -or ($assertFails.Count -gt 0)

    if (-not $timedOut) {
        if ($hasFail) {
            $detail = if ($finalLines.Count -gt 0) { $finalLines -join '; ' } else { $assertFails -join '; ' }
            $reasons.Add("log reported failure ($detail)")
        } elseif ($finalLines.Count -eq 0) {
            $reasons.Add("log is missing '[x64dbg-test] FINAL' result line")
        } elseif (-not $hasPass) {
            $reasons.Add("log did not confirm 'FINAL status=pass asserts=2' (got: $($finalLines -join '; '))")
        }
    }

    if ($reasons.Count -eq 0) {
        $passedCases++
        "[PASS] $($c.Name) (exit=$exitCode)"
    } else {
        $failedCases.Add($c.Name)
        "[FAIL] $($c.Name): $($reasons -join '; ')"
    }
}

""
if ($failedCases.Count -eq 0) {
    "SUMMARY: $passedCases/$($cases.Count) passed"
    exit 0
} else {
    "SUMMARY: $passedCases/$($cases.Count) passed; failed: $($failedCases -join ', ')"
    exit $failedCases.Count
}
