#requires -Version 7.0
param([ValidateSet('Enable','Disable','Status')][string]$Mode = 'Status', [string]$RuntimeDirectory, [switch]$BotOnly)
$ErrorActionPreference = 'Stop'
$repoPath = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
if (-not $RuntimeDirectory) { $RuntimeDirectory = Join-Path $repoPath 'runtime' }
$runtimePath = (Resolve-Path -LiteralPath $RuntimeDirectory).Path
$scriptPath = Join-Path $PSScriptRoot 'supervise-native.ps1'
$pwshPath = Join-Path $PSHOME 'pwsh.exe'
$enabledPath = Join-Path $runtimePath 'supervisor.enabled'
$statePath = Join-Path $runtimePath 'supervisor.json'
$runKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
$valueName = 'PAXVEIL'
$currentValue = (Get-ItemProperty -LiteralPath $runKey -Name $valueName -ErrorAction SilentlyContinue).$valueName
if ($currentValue -and -not $currentValue.Contains($scriptPath)) { throw 'Another PAXVEIL startup entry exists. It was not changed.' }
if ($repoPath.Contains('"') -or $runtimePath.Contains('"') -or $pwshPath.Contains('"')) { throw 'Unsupported quote in path.' }
$running = $false
if (Test-Path -LiteralPath $statePath) {
    $record = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    $process = Get-Process -Id $record.pid -ErrorAction SilentlyContinue
    $started = if ($record.started -is [datetime]) { $record.started.ToUniversalTime() } else { [DateTimeOffset]::Parse([string]$record.started).UtcDateTime }
    $running = $process -and $process.StartTime.ToUniversalTime().Ticks -eq $started.Ticks
}
if ($Mode -eq 'Enable') {
    if (-not (Test-Path -LiteralPath (Join-Path $runtimePath 'venv\Scripts\python.exe'))) { throw 'Initialize this runtime first.' }
    $argumentText = "-NoLogo -NoProfile -NonInteractive -WindowStyle Hidden -File `"$scriptPath`" -RuntimeDirectory `"$runtimePath`""
    if ($BotOnly) { $argumentText += ' -BotOnly' }
    $commandText = "`"$pwshPath`" $argumentText"
    if (-not (Test-Path -LiteralPath $runKey)) { New-Item -Path $runKey | Out-Null }
    New-ItemProperty -LiteralPath $runKey -Name $valueName -Value $commandText -PropertyType String -Force | Out-Null
    'enabled' | Set-Content -LiteralPath $enabledPath -Encoding UTF8
    if (-not $running) {
        Start-Process -FilePath $pwshPath -ArgumentList $argumentText -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtimePath 'supervisor.log') -RedirectStandardError (Join-Path $runtimePath 'supervisor.error.log') | Out-Null
        $verified = $false
        for ($attempt = 0; $attempt -lt 40; $attempt++) {
            Start-Sleep -Milliseconds 250
            if (Test-Path -LiteralPath $statePath) {
                $launched = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
                $candidate = Get-Process -Id $launched.pid -ErrorAction SilentlyContinue
                $candidateStart = if ($launched.started -is [datetime]) { $launched.started.ToUniversalTime() } else { [DateTimeOffset]::Parse([string]$launched.started).UtcDateTime }
                if ($candidate -and $candidate.StartTime.ToUniversalTime().Ticks -eq $candidateStart.Ticks) { $verified = $true; break }
            }
        }
        if (-not $verified) { throw 'Automatic launch configured, but the supervisor did not start. Inspect the private supervisor log.' }
    }
    Write-Output 'PAXVEIL supervision enabled now and after Windows sign-in.'
} elseif ($Mode -eq 'Disable') {
    if ($currentValue) { Remove-ItemProperty -LiteralPath $runKey -Name $valueName }
    if (Test-Path -LiteralPath $enabledPath) { Remove-Item -LiteralPath $enabledPath }
    Write-Output 'PAXVEIL automatic launch disabled. Running services are unchanged; use stop.ps1 to stop them.'
} else {
    [pscustomobject]@{WindowsSignIn=[bool]$currentValue; Enabled=(Test-Path -LiteralPath $enabledPath); SupervisorRunning=[bool]$running} | Format-List
}
