#requires -Version 7.0
param([switch]$Telegram, [switch]$BotOnly, [string]$RuntimeDirectory)
$ErrorActionPreference = 'Stop'
$repoPath = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$envContents = [IO.File]::ReadAllText((Join-Path $repoPath '.env'))
if ($envContents -notmatch 'DATABASE_URL=postgresql\+psycopg://paxveil:[^@]+@127\.0\.0\.1:55432/paxveil') {
    throw 'This launcher owns a local PostgreSQL cluster on port 55432. For a custom database, use the manual or Compose instructions.'
}
if (-not $RuntimeDirectory) { $RuntimeDirectory = Join-Path $repoPath 'runtime' }
$RuntimeDirectory = (Resolve-Path -LiteralPath $RuntimeDirectory).Path
$pythonPath = Join-Path $RuntimeDirectory 'venv\Scripts\python.exe'
$env:PAXVEIL_LOG_DIR = Join-Path $RuntimeDirectory 'logs'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Run scripts/init.ps1 first' }
$manifestPath = Join-Path $RuntimeDirectory 'processes.json'
if (Test-Path -LiteralPath $manifestPath) { throw 'A process manifest already exists. Run scripts/stop.ps1 before starting again.' }
if ($Telegram -and $envContents -notmatch '(?m)^TELEGRAM_BOT_TOKEN=\S+') { throw 'Set TELEGRAM_BOT_TOKEN locally in .env before starting with -Telegram.' }
function Test-LocalPort([int]$port) {
    $client = [Net.Sockets.TcpClient]::new()
    try {
        $connect = $client.ConnectAsync('127.0.0.1', $port)
        if (-not $connect.Wait(500)) { return $false }
        return $client.Connected
    } catch { return $false } finally { $client.Dispose() }
}
$requiredPorts = if ($BotOnly) { @(55432, 8000) } else { @(55432, 8000, 3000) }
foreach ($port in $requiredPorts) {
    if (Test-LocalPort $port) { throw "Local port $port is already occupied. No service was started or database changed." }
}
$records = @()
function Start-PaxveilProcess([string]$label, [string]$executable, [string[]]$arguments, [string]$directory) {
    $process = Start-Process -FilePath $executable -ArgumentList $arguments -WorkingDirectory $directory -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $RuntimeDirectory "$label.log") -RedirectStandardError (Join-Path $RuntimeDirectory "$label.error.log")
    $script:records += [pscustomobject]@{ label=$label; pid=$process.Id; started=$process.StartTime.ToUniversalTime().ToString('o'); executable=$executable }
    $script:records | ConvertTo-Json | Set-Content -LiteralPath "$manifestPath.tmp" -Encoding UTF8
    [IO.File]::Move("$manifestPath.tmp", $manifestPath, $true)
}
$binRecordPath = Join-Path $RuntimeDirectory 'postgres-bin.txt'
$pgBin = if (Test-Path -LiteralPath $binRecordPath) { (Get-Content -LiteralPath $binRecordPath -Raw).Trim() } else { 'C:\Program Files\PostgreSQL\18\bin' }
$pgData = Join-Path $RuntimeDirectory 'pgdata'
$startupLock = [IO.File]::Open((Join-Path $RuntimeDirectory 'processes.operation.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
try {
Start-PaxveilProcess 'postgres' (Join-Path $pgBin 'postgres.exe') @('-D', "`"$pgData`"", '-p', '55432', '-h', '127.0.0.1') $RuntimeDirectory
$ready = $false
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    & (Join-Path $pgBin 'pg_isready.exe') -h 127.0.0.1 -p 55432 -U paxveil -d postgres | Out-Null
    if ($LASTEXITCODE -eq 0) { $ready = $true; break }
    Start-Sleep -Seconds 1
}
if (-not $ready) { throw 'PostgreSQL did not become ready in 30 seconds; inspect its logs' }
$clusterPidPath = Join-Path $pgData 'postmaster.pid'
$clusterPid = [int](Get-Content -LiteralPath $clusterPidPath -TotalCount 1)
if ($clusterPid -ne $records[0].pid -or -not (Get-Process -Id $clusterPid -ErrorAction SilentlyContinue)) {
    throw 'The expected project-owned PostgreSQL process is not running; no migrations were executed.'
}
Push-Location (Join-Path $repoPath 'backend')
try {
    & $pythonPath -c 'from dotenv import dotenv_values; import psycopg; from pathlib import Path; v=dotenv_values(Path.cwd().parent/".env")["DATABASE_URL"].replace("postgresql+psycopg:","postgresql:"); c=psycopg.connect(v.rsplit("/",1)[0]+"/postgres",autocommit=True); exists=c.execute("SELECT 1 FROM pg_database WHERE datname=%s",("paxveil",)).fetchone(); c.execute("CREATE DATABASE paxveil") if not exists else None'
    if ($LASTEXITCODE -ne 0) { throw 'Database not ready; check runtime/postgres.error.log' }
    & $pythonPath -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'Migration failed' }
} finally { Pop-Location }
Start-PaxveilProcess 'api' $pythonPath @('-m','uvicorn','paxveil.api:app','--host','127.0.0.1','--port','8000','--no-access-log') (Join-Path $repoPath 'backend')
Start-PaxveilProcess 'worker' $pythonPath @('-m','paxveil.worker') (Join-Path $repoPath 'backend')
if (-not $BotOnly) {
    $nodePath = (Get-Command node.exe).Source
    Start-PaxveilProcess 'web' $nodePath @('node_modules\next\dist\bin\next','start','--hostname','127.0.0.1','--port','3000') (Join-Path $repoPath 'frontend')
}
if ($Telegram) { Start-PaxveilProcess 'bot' $pythonPath @('-m','paxveil.bot') (Join-Path $repoPath 'backend') }
$healthUrls = if ($BotOnly) { @('http://127.0.0.1:8000/api/health') } else { @('http://127.0.0.1:8000/api/health', 'http://127.0.0.1:3000/') }
foreach ($url in $healthUrls) {
    $httpReady = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        try {
            $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200) { $httpReady = $true; break }
        } catch { }
        Start-Sleep -Seconds 1
    }
    if (-not $httpReady) { throw "Service did not become ready: $url. Inspect logs, then run scripts/stop.ps1." }
}
Write-Output 'PAXVEIL: http://localhost:3000 | API: http://127.0.0.1:8000/docs'
} finally { $startupLock.Dispose() }
