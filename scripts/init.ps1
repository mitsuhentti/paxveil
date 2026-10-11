#requires -Version 7.0
param([string]$Python = 'py', [string]$PostgresBin = 'C:\Program Files\PostgreSQL\18\bin', [string]$RuntimeDirectory)
$ErrorActionPreference = 'Stop'
$repoPath = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$runtimePath = if ($RuntimeDirectory) { [IO.Path]::GetFullPath($RuntimeDirectory) } else { Join-Path $repoPath 'runtime' }
New-Item -ItemType Directory -Force -Path $runtimePath | Out-Null
$pythonPath = Join-Path $runtimePath 'venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    if ($Python -eq 'py') { & py -3.11 -m venv (Join-Path $runtimePath 'venv') }
    else { & $Python -m venv (Join-Path $runtimePath 'venv') }
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 virtual environment could not be created' }
}
& $pythonPath -m pip install --quiet --disable-pip-version-check -r (Join-Path $repoPath 'backend\requirements.lock')
if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed' }
$envPath = Join-Path $repoPath '.env'
if (-not (Test-Path -LiteralPath $envPath)) {
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $bytes = New-Object byte[] 32
    $rng.GetBytes($bytes)
    $databasePassword = ([BitConverter]::ToString($bytes)).Replace('-','').ToLowerInvariant()
    $rng.GetBytes($bytes)
    $botKey = ([BitConverter]::ToString($bytes)).Replace('-','').ToLowerInvariant()
    $example = [IO.File]::ReadAllText((Join-Path $repoPath '.env.example'))
    $example = $example.Replace('CHANGE_ME',$databasePassword).Replace('GENERATE_RANDOM_64_HEX_CHARACTERS',$botKey)
    $example = $example.Replace('./runtime/cache', ((Join-Path $runtimePath 'cache').Replace('\','/')))
    [IO.File]::WriteAllText($envPath, $example)
}
# Older native configurations did not include the Compose password setting.
$envContents = [IO.File]::ReadAllText($envPath)
if ($envContents -notmatch '(?m)^POSTGRES_PASSWORD=') {
    $localPassword = [regex]::Match($envContents, 'DATABASE_URL=postgresql\+psycopg://paxveil:([^@]+)@127\.0\.0\.1:55432/paxveil')
    if ($localPassword.Success) {
        [IO.File]::AppendAllText($envPath, [Environment]::NewLine + 'POSTGRES_PASSWORD=' + $localPassword.Groups[1].Value + [Environment]::NewLine)
    }
}
if (-not (Test-Path -LiteralPath (Join-Path $PostgresBin 'initdb.exe'))) {
    throw 'PostgreSQL binaries missing; use Docker Compose or pass -PostgresBin with an installed PostgreSQL bin directory'
}
$dataPath = Join-Path $runtimePath 'pgdata'
if (-not (Test-Path -LiteralPath (Join-Path $dataPath 'PG_VERSION'))) {
    $envContents = [IO.File]::ReadAllText($envPath)
    $match = [regex]::Match($envContents, 'DATABASE_URL=postgresql\+psycopg://paxveil:([^@]+)@127\.0\.0\.1:55432/paxveil')
    if (-not $match.Success) { throw 'Custom DATABASE_URL detected. Initialize that database separately; no database was changed.' }
    $passwordPath = Join-Path $runtimePath 'pg-password.tmp'
    [IO.File]::WriteAllText($passwordPath, $match.Groups[1].Value)
    try {
        & (Join-Path $PostgresBin 'initdb.exe') -D $dataPath -U paxveil --auth=scram-sha-256 --pwfile=$passwordPath --encoding=UTF8 --locale=C
        if ($LASTEXITCODE -ne 0) { throw 'initdb failed' }
    } finally { Remove-Item -LiteralPath $passwordPath }
}
Set-Content -LiteralPath (Join-Path $runtimePath 'postgres-bin.txt') -Value $PostgresBin
Push-Location (Join-Path $repoPath 'frontend')
try {
    & npm.cmd ci --cache (Join-Path $runtimePath 'npm-cache')
    if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed' }
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
} finally { Pop-Location }
Write-Output 'Initialized. Start with .\scripts\start.ps1. Local secrets remain in ignored .env.'
