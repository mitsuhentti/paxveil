#requires -Version 7.0
param([string]$RuntimeDirectory, [switch]$ForceDatabase)
$ErrorActionPreference = 'Stop'
$repoPath = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if (-not $RuntimeDirectory) { $RuntimeDirectory = Join-Path $repoPath 'runtime' }
$manifestPath = Join-Path $RuntimeDirectory 'processes.json'
if (-not (Test-Path -LiteralPath $manifestPath)) { Write-Output 'No PAXVEIL process manifest'; return }
$records = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
foreach ($record in @($records)[(@($records).Count-1)..0]) {
    $process = Get-Process -Id $record.pid -ErrorAction SilentlyContinue
    if (-not $process) { continue }
    # PowerShell 7.5 parses JSON ISO dates automatically; Windows PowerShell keeps strings.
    $recordedStart = if ($record.started -is [datetime]) { $record.started.ToUniversalTime() } else { [DateTimeOffset]::Parse([string]$record.started).UtcDateTime }
    if ($process.StartTime.ToUniversalTime().Ticks -ne $recordedStart.Ticks) { throw "PID $($record.pid) has been reused; no process killed" }
    if ($record.label -eq 'postgres') {
        $pgBin = Split-Path $record.executable
        & (Join-Path $pgBin 'pg_ctl.exe') -D (Join-Path $RuntimeDirectory 'pgdata') -m fast -t 10 -w stop
        if ($LASTEXITCODE -ne 0) {
            if (-not $ForceDatabase) { throw 'PostgreSQL stop failed; manifest retained. If this project-owned development cluster is blocked by Windows isolation, retry with -ForceDatabase. WAL recovery will run on next start.' }
            Write-Warning 'Force-stopping the verified project-owned development PostgreSQL tree. Next start requires WAL recovery.'
            $process.Kill($true)
            if (-not $process.WaitForExit(10000)) { throw 'PostgreSQL force stop timed out; manifest retained' }
        }
    } else {
        # Kill only this verified process tree; taskkill requires broader OS enumeration.
        $process.Kill($true)
        if (-not $process.WaitForExit(10000)) { throw 'Process stop timed out; process manifest retained' }
    }
}
Remove-Item -LiteralPath $manifestPath
Write-Output 'PAXVEIL stopped. Database and source snapshots retained.'
