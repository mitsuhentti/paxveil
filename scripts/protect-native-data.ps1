#requires -Version 7.0
param([Parameter(Mandatory)][string]$RuntimeDirectory)
$ErrorActionPreference = 'Stop'
$repoPath = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$runtimePath = (Resolve-Path -LiteralPath $RuntimeDirectory).Path
. (Join-Path $PSScriptRoot 'native-paths.ps1')
$backupPath = Get-PaxveilBackupDirectory $repoPath $runtimePath
$pgData = Join-Path $runtimePath 'pgdata'
$rotatingLogs = Join-Path $runtimePath 'logs'
function Get-VerifiedRuntimeFile([string]$FilePath) {
    $resolvedFile = (Resolve-Path -LiteralPath $FilePath).ProviderPath
    $parentPath = Split-Path -Parent $resolvedFile
    if (-not $parentPath.Equals($runtimePath, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Refusing to encrypt a file outside the runtime root.'
    }
    $item = Get-Item -LiteralPath $resolvedFile -Force
    if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'Runtime root files must be ordinary files, not links or directories.'
    }
    return $resolvedFile
}
if (-not (Test-Path -LiteralPath (Join-Path $pgData 'PG_VERSION'))) { throw 'No project PostgreSQL cluster found.' }
if (Test-Path -LiteralPath (Join-Path $runtimePath 'processes.json')) { throw 'Stop PAXVEIL before protecting its data.' }
$probe = [Net.Sockets.TcpClient]::new()
try {
    $connect = $probe.ConnectAsync('127.0.0.1',55432)
    if ($connect.Wait(500) -and $probe.Connected) { throw 'PostgreSQL port is occupied. No encryption settings changed.' }
} finally { $probe.Dispose() }
$cipherPath = Join-Path $env:SystemRoot 'System32\cipher.exe'
if (-not (Test-Path -LiteralPath $cipherPath)) { throw 'Windows EFS is unavailable; use an encrypted storage volume.' }
# Fail before any encryption or log redirection if a root file resolves unsafely.
foreach ($file in @(Get-ChildItem -LiteralPath $runtimePath -Force -File)) {
    Get-VerifiedRuntimeFile $file.FullName | Out-Null
}
New-Item -ItemType Directory -Path $backupPath -Force | Out-Null
New-Item -ItemType Directory -Path $rotatingLogs -Force | Out-Null
if ((Get-Item -LiteralPath $rotatingLogs -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
    throw 'The runtime log directory must not be a link.'
}
$logPath = Join-Path $runtimePath 'encryption-operations.log'
& $cipherPath /e /a $runtimePath *> $logPath
if ($LASTEXITCODE -ne 0) { throw 'Runtime directory encryption failed.' }
& $cipherPath /e /a (Join-Path $repoPath '.env') *>> $logPath
if ($LASTEXITCODE -ne 0) { throw 'Local secret file encryption failed.' }
foreach ($directory in @($pgData, $backupPath, $rotatingLogs)) {
    & $cipherPath /e /a "/s:$directory" *>> $logPath
    if ($LASTEXITCODE -ne 0) { throw 'Project data encryption failed; inspect the private operations log.' }
    $unencrypted = @(Get-ChildItem -LiteralPath $directory -Recurse -Force -File | Where-Object { -not ($_.Attributes -band [IO.FileAttributes]::Encrypted) })
    if ($unencrypted.Count) { throw 'Some project data files remain unencrypted.' }
}
# Existing root files predate the encrypted-directory inheritance setting.
# Do not recurse over the runtime: Python and downloaded binaries stay untouched.
foreach ($file in @(Get-ChildItem -LiteralPath $runtimePath -Force -File | Where-Object { $_.FullName -ne $logPath })) {
    $verifiedFile = Get-VerifiedRuntimeFile $file.FullName
    & $cipherPath /e /a $verifiedFile *>> $logPath
    if ($LASTEXITCODE -ne 0) { throw 'Runtime file encryption failed; inspect the private operations log.' }
    if (-not ((Get-Item -LiteralPath $verifiedFile -Force).Attributes -band [IO.FileAttributes]::Encrypted)) {
        throw 'A runtime root file remains unencrypted.'
    }
}
# Encrypt this file last, with no redirect that would keep the target open.
$verifiedLog = Get-VerifiedRuntimeFile $logPath
& $cipherPath /e /a $verifiedLog *> $null
if ($LASTEXITCODE -ne 0) { throw 'Encryption operations log protection failed.' }
foreach ($path in @($runtimePath, $pgData, $backupPath, $rotatingLogs, (Join-Path $repoPath '.env'), $verifiedLog)) {
    if (-not ((Get-Item -LiteralPath $path -Force).Attributes -band [IO.FileAttributes]::Encrypted)) { throw 'Encryption verification failed.' }
}
$unprotectedRootFiles = @(Get-ChildItem -LiteralPath $runtimePath -Force -File | Where-Object { -not ($_.Attributes -band [IO.FileAttributes]::Encrypted) })
if ($unprotectedRootFiles.Count) { throw 'Some runtime root files remain unencrypted.' }
Write-Output 'Project database, private backups, runtime root files, logs and local secrets use Windows EFS. Its key is held by your Windows user certificate store; preserve that certificate before reinstalling Windows or moving encrypted files.'
