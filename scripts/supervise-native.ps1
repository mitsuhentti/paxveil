#requires -Version 7.0
param([Parameter(Mandatory)][string]$RuntimeDirectory, [switch]$BotOnly, [ValidateRange(5,60)][int]$PollSeconds = 10)
$ErrorActionPreference = 'Stop'
$repoPath = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$runtimePath = (Resolve-Path -LiteralPath $RuntimeDirectory).Path
$enabledPath = Join-Path $runtimePath 'supervisor.enabled'
$lockPath = Join-Path $runtimePath 'supervisor.lock'
$statePath = Join-Path $runtimePath 'supervisor.json'
$manifestPath = Join-Path $runtimePath 'processes.json'
$pythonPath = Join-Path $runtimePath 'venv\Scripts\python.exe'
. (Join-Path $PSScriptRoot 'native-paths.ps1')
$backupPath = Get-PaxveilBackupDirectory $repoPath $runtimePath
$env:PAXVEIL_LOG_DIR = Join-Path $runtimePath 'logs'
$pgBin = (Get-Content -LiteralPath (Join-Path $runtimePath 'postgres-bin.txt') -Raw).Trim()
$mutex = $null
try { $mutex = [IO.File]::Open($lockPath, 'OpenOrCreate', 'ReadWrite', 'None') }
catch { Write-Output 'A PAXVEIL supervisor is already running.'; exit 0 }
Add-Type -TypeDefinition @'
using System.Runtime.InteropServices;
public static class PaxveilNativePower {
    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern uint SetThreadExecutionState(uint flags);
}
'@

function Write-SupervisorEvent([string]$event) {
    $logPath = Join-Path $runtimePath 'supervisor-events.log'
    if ((Test-Path -LiteralPath $logPath) -and (Get-Item -LiteralPath $logPath).Length -gt 5242880) {
        [IO.File]::Copy($logPath, "$logPath.previous", $true)
        [IO.File]::WriteAllText($logPath, '')
    }
    Add-Content -LiteralPath $logPath -Value "$([datetime]::UtcNow.ToString('o')) $event"
}
function Get-OwnedProcess($record) {
    try {
        $candidate = Get-Process -Id $record.pid -ErrorAction SilentlyContinue
        if (-not $candidate -or -not $candidate.StartTime) { return $null }
        $started = if ($record.started -is [datetime]) { $record.started.ToUniversalTime() } else { [DateTimeOffset]::Parse([string]$record.started).UtcDateTime }
        if ($candidate.StartTime.ToUniversalTime().Ticks -ne $started.Ticks) { return $null }
        return $candidate
    } catch { return $null }
}
function Save-Manifest($records) {
    $temporary = "$manifestPath.tmp"
    @($records) | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $temporary -Encoding UTF8
    [IO.File]::Move($temporary, $manifestPath, $true)
}
function Restart-Component([string]$label, $records) {
    $operationLock = [IO.File]::Open((Join-Path $runtimePath 'processes.operation.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
    try {
    if (-not (Test-Path -LiteralPath $enabledPath)) { return }
    $directory = Join-Path $repoPath 'backend'
    switch ($label) {
        'postgres' { $executable = Join-Path $pgBin 'postgres.exe'; $arguments = @('-D', "`"$(Join-Path $runtimePath 'pgdata')`"", '-p','55432','-h','127.0.0.1'); $directory = $runtimePath }
        'api' { $executable = $pythonPath; $arguments = @('-m','uvicorn','paxveil.api:app','--host','127.0.0.1','--port','8000','--no-access-log') }
        'worker' { $executable = $pythonPath; $arguments = @('-m','paxveil.worker') }
        'bot' { $executable = $pythonPath; $arguments = @('-m','paxveil.bot') }
        'web' { $executable = (Get-Command node.exe).Source; $arguments = @('node_modules\next\dist\bin\next','start','--hostname','127.0.0.1','--port','3000'); $directory = Join-Path $repoPath 'frontend' }
        default { throw 'Unknown component; no process started.' }
    }
    foreach ($suffix in @('.log','.error.log')) {
        $log = Join-Path $runtimePath "$label$suffix"
        if (Test-Path -LiteralPath $log) { [IO.File]::Copy($log, "$log.previous", $true) }
    }
    $child = Start-Process -FilePath $executable -ArgumentList $arguments -WorkingDirectory $directory -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtimePath "$label.log") -RedirectStandardError (Join-Path $runtimePath "$label.error.log")
    $next = @($records | Where-Object label -ne $label) + [pscustomobject]@{ label=$label; pid=$child.Id; started=$child.StartTime.ToUniversalTime().ToString('o'); executable=$executable }
    Save-Manifest $next
    Write-SupervisorEvent "$label restarted"
    } finally { $operationLock.Dispose() }
}

$own = Get-Process -Id $PID
@{pid=$PID; started=$own.StartTime.ToUniversalTime().ToString('o'); repo=$repoPath; runtime=$runtimePath; bot_only=[bool]$BotOnly} | ConvertTo-Json | Set-Content -LiteralPath "$statePath.tmp" -Encoding UTF8
[IO.File]::Move("$statePath.tmp", $statePath, $true)
$failureCount = 0
$apiFailures = 0
$backupAttempt = [datetime]::MinValue
try {
    Write-SupervisorEvent 'supervisor started'
    if ([PaxveilNativePower]::SetThreadExecutionState([uint32]2147483649)) {
        Write-SupervisorEvent 'automatic idle sleep prevented while supervisor runs; display settings unchanged'
    } else { Write-SupervisorEvent 'Windows awake request failed; check idle sleep settings' }
    while (Test-Path -LiteralPath $enabledPath) {
        try {
            $records = if (Test-Path -LiteralPath $manifestPath) { @(Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json) } else { @() }
            if ($records.Count -gt 0 -and -not @($records | Where-Object { Get-OwnedProcess $_ }).Count) {
                $archivedPath = Join-Path $runtimePath "processes-stale-$([datetime]::UtcNow.ToString('yyyyMMddHHmmssfff')).json"
                [IO.File]::Move($manifestPath, $archivedPath)
                $records = @()
            }
            if ($records.Count -eq 0) {
                & (Join-Path $PSScriptRoot 'start.ps1') -Telegram -BotOnly:$BotOnly -RuntimeDirectory $runtimePath
            } else {
                $required = if ($BotOnly) { @('postgres','api','worker','bot') } else { @('postgres','api','worker','web','bot') }
                foreach ($label in $required) {
                    $record = $records | Where-Object label -eq $label | Select-Object -First 1
                    if (-not $record -or -not (Get-OwnedProcess $record)) {
                        Restart-Component $label $records
                        $records = @(Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json)
                        if ($label -eq 'postgres') { break }
                    }
                }
            }
            try {
                $response = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/api/health' -TimeoutSec 3 -UseBasicParsing
                if ($response.StatusCode -ne 200) { throw 'Unhealthy API' }
                $apiFailures = 0
            } catch { $apiFailures++ }
            if ($apiFailures -ge 3 -and (Test-Path -LiteralPath $enabledPath)) {
                $records = @(Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json)
                $apiRecord = $records | Where-Object label -eq 'api' | Select-Object -First 1
                if ($apiRecord) {
                    $apiProcess = Get-OwnedProcess $apiRecord
                    if ($apiProcess) { $apiProcess.Kill($true); [void]$apiProcess.WaitForExit(10000) }
                    Restart-Component 'api' $records
                }
                $apiFailures = 0
            }
            $lastBackupPath = Join-Path $runtimePath 'backup-last-success.txt'
            $lastBackup = if (Test-Path -LiteralPath $lastBackupPath) { [datetime]::Parse((Get-Content -LiteralPath $lastBackupPath -Raw).Trim()).ToUniversalTime() } else { [datetime]::MinValue }
            if ($apiFailures -eq 0 -and ([datetime]::UtcNow - $lastBackup).TotalHours -ge 24 -and ([datetime]::UtcNow - $backupAttempt).TotalHours -ge 1) {
                $backupAttempt = [datetime]::UtcNow
                & $pythonPath (Join-Path $PSScriptRoot 'database-ops.py') backup --env (Join-Path $repoPath '.env') --pg-bin $pgBin --directory $backupPath *> (Join-Path $runtimePath 'backup-operations.log')
                if ($LASTEXITCODE -eq 0) {
                    [datetime]::UtcNow.ToString('o') | Set-Content -LiteralPath $lastBackupPath
                    Write-SupervisorEvent 'daily backup completed'
                } else { Write-SupervisorEvent 'daily backup failed; retry in one hour' }
            }
            $failureCount = 0
        } catch {
            $failureCount++
            Write-SupervisorEvent "supervisor operation failed ($($_.Exception.GetType().Name), script line $($_.InvocationInfo.ScriptLineNumber)); retry pending"
        }
        Start-Sleep -Seconds ([Math]::Min(300, $PollSeconds * [Math]::Pow(2,[Math]::Min($failureCount,5))))
    }
} finally {
    [void][PaxveilNativePower]::SetThreadExecutionState([uint32]2147483648)
    Write-SupervisorEvent 'supervisor stopped'
    $mutex.Dispose()
    if (Test-Path -LiteralPath $statePath) { Remove-Item -LiteralPath $statePath }
}
