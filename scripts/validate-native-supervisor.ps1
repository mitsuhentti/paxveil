#requires -Version 7.0
param(
    [Parameter(Mandatory)][string]$PythonExecutable,
    [string]$WorkDirectory,
    [string]$OutputPath
)
$ErrorActionPreference = 'Stop'
if (-not $IsWindows) { throw 'This check validates the Windows native supervisor.' }
$repositoryPath = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$pythonSource = (Resolve-Path -LiteralPath $PythonExecutable).Path
if (-not $WorkDirectory) {
    $WorkDirectory = Join-Path $repositoryPath "runtime\validation\supervisor-$([guid]::NewGuid().ToString('N'))"
}
if (Test-Path -LiteralPath $WorkDirectory) { throw 'Use a new, empty validation directory.' }
$null = New-Item -ItemType Directory -Path $WorkDirectory
$workPath = (Resolve-Path -LiteralPath $WorkDirectory).Path
$fixtureRepo = Join-Path $workPath 'fixture'
$fixtureScripts = Join-Path $fixtureRepo 'scripts'
$fixtureBackend = Join-Path $fixtureRepo 'backend'
$fixtureRuntime = Join-Path $fixtureRepo 'runtime'
$fixturePackage = Join-Path $fixtureBackend 'paxveil'
foreach ($directory in @($fixtureScripts, $fixtureRuntime, $fixturePackage)) {
    $null = New-Item -ItemType Directory -Path $directory -Force
}
if (-not $OutputPath) { $OutputPath = Join-Path $repositoryPath 'docs\NATIVE_SUPERVISOR_VALIDATION.json' }
$outputFullPath = [IO.Path]::GetFullPath($OutputPath)
$enabledFile = Join-Path $fixtureRuntime 'supervisor.enabled'
$manifestFile = Join-Path $fixtureRuntime 'processes.json'
$stateFile = Join-Path $fixtureRuntime 'supervisor.json'
$launchCountFile = Join-Path $fixtureRuntime 'fixture-launch-count.txt'
$pwshExecutable = Join-Path $PSHOME 'pwsh.exe'
$supervisor = $null
$extraSupervisor = $null
$knownRecords = [Collections.Generic.List[object]]::new()
$checks = [ordered]@{}
$failureType = $null
$began = [datetime]::UtcNow

function Wait-ValidationCondition([scriptblock]$Condition, [string]$Description, [int]$TimeoutSeconds = 30) {
    $deadline = [datetime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        if (& $Condition) { return }
        Start-Sleep -Milliseconds 100
    } while ([datetime]::UtcNow -lt $deadline)
    throw "Validation timeout: $Description"
}
function Read-FixtureManifest {
    if (-not (Test-Path -LiteralPath $manifestFile)) { return @() }
    return @(Get-Content -LiteralPath $manifestFile -Raw | ConvertFrom-Json)
}
function Save-KnownRecords($Records) {
    foreach ($record in @($Records)) { $knownRecords.Add($record) }
}
function Stop-VerifiedFixtureProcess($Record) {
    $candidate = Get-Process -Id $Record.pid -ErrorAction SilentlyContinue
    if (-not $candidate) { return }
    $timestamp = if ($Record.started -is [datetime]) { $Record.started.ToUniversalTime() } else { [DateTimeOffset]::Parse([string]$Record.started).UtcDateTime }
    if ($candidate.StartTime.ToUniversalTime().Ticks -ne $timestamp.Ticks) { return }
    $candidate.Kill($false)
    if (-not $candidate.WaitForExit(10000)) { throw 'A verified fixture child did not stop.' }
}
function Start-FixtureSupervisor([string]$Label) {
    $wrapperFile = Join-Path $fixtureScripts 'fixture-supervisor.ps1'
    return Start-Process -FilePath $pwshExecutable -ArgumentList @('-NoLogo', '-NoProfile', '-NonInteractive', '-File', "`"$wrapperFile`"", '-RuntimeDirectory', "`"$fixtureRuntime`"") -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $workPath "$Label.log") -RedirectStandardError (Join-Path $workPath "$Label.error.log")
}
function Stop-FixtureSupervisor($Process) {
    if (Test-Path -LiteralPath $enabledFile) { Remove-Item -LiteralPath $enabledFile }
    if (-not $Process) { return }
    if (-not $Process.HasExited -and -not $Process.WaitForExit(20000)) {
        $live = Get-Process -Id $Process.Id -ErrorAction SilentlyContinue
        if ($live -and $live.StartTime.ToUniversalTime().Ticks -eq $Process.StartTime.ToUniversalTime().Ticks) {
            $live.Kill($false)
            [void]$live.WaitForExit(10000)
        }
        throw 'The fixture supervisor did not stop after its enable flag was removed.'
    }
}

try {
    foreach ($name in @('supervise-native.ps1', 'native-paths.ps1')) {
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination (Join-Path $fixtureScripts $name)
    }
    $checks.exact_supervisor_copy = (Get-FileHash -LiteralPath (Join-Path $fixtureScripts 'supervise-native.ps1')).Hash -eq (Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'supervise-native.ps1')).Hash
    $checks.exact_paths_helper_copy = (Get-FileHash -LiteralPath (Join-Path $fixtureScripts 'native-paths.ps1')).Hash -eq (Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'native-paths.ps1')).Hash
    & $pythonSource -m venv --without-pip (Join-Path $fixtureRuntime 'venv')
    if ($LASTEXITCODE -ne 0) { throw 'Unable to create the isolated standard-library Python environment.' }
    '' | Set-Content -LiteralPath (Join-Path $fixturePackage '__init__.py') -Encoding UTF8
    @'
import time
print("isolated supervisor fixture; no network or database", flush=True)
time.sleep(300)
'@ | Set-Content -LiteralPath (Join-Path $fixturePackage 'worker.py') -Encoding UTF8
    # The supervisor's health dependency is controlled here, not a real listener.
    @'
param([Parameter(Mandatory)][string]$RuntimeDirectory)
function Invoke-WebRequest {
    param([string]$Uri, [int]$TimeoutSec, [switch]$UseBasicParsing)
    if ($Uri -ne 'http://127.0.0.1:8000/api/health') { throw 'Unexpected fixture health URL.' }
    Add-Content -LiteralPath (Join-Path $RuntimeDirectory 'fixture-health-probes.txt') -Value 'controlled healthy response'
    return [pscustomobject]@{ StatusCode = 200 }
}
& (Join-Path $PSScriptRoot 'supervise-native.ps1') -RuntimeDirectory $RuntimeDirectory -BotOnly -PollSeconds 5
'@ | Set-Content -LiteralPath (Join-Path $fixtureScripts 'fixture-supervisor.ps1') -Encoding UTF8
    @'
param([switch]$Telegram, [switch]$BotOnly, [Parameter(Mandatory)][string]$RuntimeDirectory)
$ErrorActionPreference = 'Stop'
$fixtureRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$pythonPath = Join-Path $RuntimeDirectory 'venv\Scripts\python.exe'
$manifestPath = Join-Path $RuntimeDirectory 'processes.json'
$operationLock = [IO.File]::Open((Join-Path $RuntimeDirectory 'processes.operation.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
try {
    $records = @()
    foreach ($label in @('postgres','api','worker','bot')) {
        $child = Start-Process -FilePath $pythonPath -ArgumentList @('-m','paxveil.worker') -WorkingDirectory (Join-Path $fixtureRoot 'backend') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $RuntimeDirectory "$label.log") -RedirectStandardError (Join-Path $RuntimeDirectory "$label.error.log")
        $records += [pscustomobject]@{ label=$label; pid=$child.Id; started=$child.StartTime.ToUniversalTime().ToString('o'); executable=$pythonPath }
        $records | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath "$manifestPath.tmp" -Encoding UTF8
        [IO.File]::Move("$manifestPath.tmp", $manifestPath, $true)
    }
    $countPath = Join-Path $RuntimeDirectory 'fixture-launch-count.txt'
    $launches = if (Test-Path -LiteralPath $countPath) { [int](Get-Content -LiteralPath $countPath -Raw) } else { 0 }
    ($launches + 1) | Set-Content -LiteralPath $countPath
} finally { $operationLock.Dispose() }
'@ | Set-Content -LiteralPath (Join-Path $fixtureScripts 'start.ps1') -Encoding UTF8
    # No actual PostgreSQL binary is supplied; healthy fixture roles never invoke it.
    (Join-Path $workPath 'no-postgres-binary') | Set-Content -LiteralPath (Join-Path $fixtureRuntime 'postgres-bin.txt')
    [datetime]::UtcNow.ToString('o') | Set-Content -LiteralPath (Join-Path $fixtureRuntime 'backup-last-success.txt')
    'enabled' | Set-Content -LiteralPath $enabledFile
    $supervisor = Start-FixtureSupervisor 'initial-supervisor'
    Wait-ValidationCondition {
        $rows = @(Read-FixtureManifest)
        return $rows.Count -eq 4 -and (Test-Path -LiteralPath $stateFile) -and (Test-Path -LiteralPath $launchCountFile)
    } 'initial fixture launch'
    $initial = @(Read-FixtureManifest)
    Save-KnownRecords $initial
    $checks.initial_four_roles_started = $initial.Count -eq 4 -and [int](Get-Content -LiteralPath $launchCountFile -Raw) -eq 1

    # Execute only the exact trusted function definition, not the supervisor body.
    $parseTokens = $null; $parseErrors = $null
    $ast = [Management.Automation.Language.Parser]::ParseFile((Join-Path $fixtureScripts 'supervise-native.ps1'), [ref]$parseTokens, [ref]$parseErrors)
    if ($parseErrors.Count) { throw 'Supervisor source did not parse.' }
    $ownedFunction = $ast.Find({ param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Get-OwnedProcess' }, $true)
    . ([scriptblock]::Create($ownedFunction.Extent.Text))
    $worker = $initial | Where-Object label -eq 'worker' | Select-Object -First 1
    $checks.correct_start_time_recognized = $null -ne (Get-OwnedProcess $worker)
    $checks.initial_all_four_alive = @($initial | Where-Object { Get-OwnedProcess $_ }).Count -eq 4
    $workerStarted = if ($worker.started -is [datetime]) { $worker.started.ToUniversalTime() } else { [DateTimeOffset]::Parse([string]$worker.started).UtcDateTime }
    $mismatched = [pscustomobject]@{ pid=$worker.pid; started=$workerStarted.AddTicks(1).ToString('o') }
    $checks.simulated_pid_reuse_fenced = $null -eq (Get-OwnedProcess $mismatched)
    . (Join-Path $fixtureScripts 'native-paths.ps1')
    $checks.backups_inside_repo_redirected = (Get-PaxveilBackupDirectory $fixtureRepo $fixtureRuntime) -eq (Join-Path $workPath 'paxveil-private-backups')
    $checks.external_runtime_backups_stay_private = (Get-PaxveilBackupDirectory $fixtureRepo $workPath) -eq (Join-Path $workPath 'backups')

    $initialState = Get-Content -LiteralPath $stateFile -Raw
    $extraSupervisor = Start-FixtureSupervisor 'duplicate-supervisor'
    if (-not $extraSupervisor.WaitForExit(10000)) { throw 'The duplicate supervisor did not exit.' }
    $duplicateOutput = Get-Content -LiteralPath (Join-Path $workPath 'duplicate-supervisor.log') -Raw
    $checks.duplicate_supervisor_lock = $extraSupervisor.ExitCode -eq 0 -and $duplicateOutput.Contains('already running') -and (Get-Content -LiteralPath $stateFile -Raw) -eq $initialState -and [int](Get-Content -LiteralPath $launchCountFile -Raw) -eq 1

    Stop-VerifiedFixtureProcess $worker
    Wait-ValidationCondition {
        $replacement = @(Read-FixtureManifest) | Where-Object label -eq 'worker' | Select-Object -First 1
        return $replacement -and $replacement.pid -ne $worker.pid -and $null -ne (Get-OwnedProcess $replacement)
    } 'terminated fixture worker recovery'
    $recovered = @(Read-FixtureManifest)
    Save-KnownRecords $recovered
    $checks.terminated_worker_restarted = @($recovered | Where-Object label -eq 'worker').Count -eq 1
    $checks.other_roles_preserved_on_worker_restart = @($initial | Where-Object label -ne 'worker' | Where-Object { $previous=$_; -not @($recovered | Where-Object { $_.label -eq $previous.label -and $_.pid -eq $previous.pid }).Count }).Count -eq 0

    Stop-FixtureSupervisor $supervisor
    $checks.disable_flag_stops_supervisor = $supervisor.HasExited -and -not (Test-Path -LiteralPath $stateFile)
    foreach ($record in $recovered) { Stop-VerifiedFixtureProcess $record }
    $checks.stale_manifest_kept_for_recovery = (Test-Path -LiteralPath $manifestFile) -and @($recovered | Where-Object { Get-OwnedProcess $_ }).Count -eq 0
    'enabled' | Set-Content -LiteralPath $enabledFile
    $supervisor = Start-FixtureSupervisor 'relaunch-supervisor'
    Wait-ValidationCondition {
        return (Test-Path -LiteralPath $launchCountFile) -and [int](Get-Content -LiteralPath $launchCountFile -Raw) -eq 2 -and @(Read-FixtureManifest).Count -eq 4
    } 'stale manifest recovery after supervisor relaunch'
    $relaunched = @(Read-FixtureManifest)
    Save-KnownRecords $relaunched
    $archived = @(Get-ChildItem -LiteralPath $fixtureRuntime -Filter 'processes-stale-*.json')
    $checks.stale_manifest_archived = $archived.Count -eq 1 -and @(Get-Content -LiteralPath $archived[0].FullName -Raw | ConvertFrom-Json).Count -eq 4
    $checks.all_roles_relaunched = @($relaunched | Where-Object { Get-OwnedProcess $_ }).Count -eq 4
    $checks.health_dependency_mocked = (Test-Path -LiteralPath (Join-Path $fixtureRuntime 'fixture-health-probes.txt'))
    $checks.no_backup_job_executed = -not (Test-Path -LiteralPath (Join-Path $fixtureRuntime 'backup-operations.log'))
    $checks.tested_sources_still_current = (Get-FileHash -LiteralPath (Join-Path $fixtureScripts 'supervise-native.ps1')).Hash -eq (Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'supervise-native.ps1')).Hash -and (Get-FileHash -LiteralPath (Join-Path $fixtureScripts 'native-paths.ps1')).Hash -eq (Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'native-paths.ps1')).Hash
    if (@($checks.Values | Where-Object { $_ -ne $true }).Count) { throw 'One or more supervisor checks failed.' }
} catch {
    $failureType = $_.Exception.GetType().Name
} finally {
    try { Stop-FixtureSupervisor $supervisor } catch { $checks.cleanup_supervisor = $false }
    if ($extraSupervisor -and -not $extraSupervisor.HasExited) {
        $record = [pscustomobject]@{ pid=$extraSupervisor.Id; started=$extraSupervisor.StartTime.ToUniversalTime().ToString('o') }
        Stop-VerifiedFixtureProcess $record
    }
    Save-KnownRecords @(Read-FixtureManifest)
    foreach ($record in $knownRecords) {
        try { Stop-VerifiedFixtureProcess $record }
        catch { if (-not $failureType) { $failureType = $_.Exception.GetType().Name } }
    }
    $checks.fixture_children_stopped = @($knownRecords | Where-Object {
        $candidate=Get-Process -Id $_.pid -ErrorAction SilentlyContinue
        $timestamp=if ($_.started -is [datetime]) { $_.started.ToUniversalTime() } else { [DateTimeOffset]::Parse([string]$_.started).UtcDateTime }
        $candidate -and $candidate.StartTime.ToUniversalTime().Ticks -eq $timestamp.Ticks
    }).Count -eq 0
    $evidence = [ordered]@{
        schema_version = 1
        started_at = $began.ToString('o')
        finished_at = [datetime]::UtcNow.ToString('o')
        platform = 'Windows / PowerShell 7'
        method = 'Exact supervisor/helper copies; isolated standard-library Python children; mocked health response; no real database, Telegram calls, port listeners or registry changes'
        reboot_performed = $false
        pid_reuse_method = 'A live fixture PID with a deliberately mismatched recorded start timestamp; no forced OS PID reuse'
        source_sha256 = [ordered]@{
            supervisor = if (Test-Path -LiteralPath (Join-Path $fixtureScripts 'supervise-native.ps1')) { (Get-FileHash -LiteralPath (Join-Path $fixtureScripts 'supervise-native.ps1')).Hash.ToLowerInvariant() } else { $null }
            paths_helper = if (Test-Path -LiteralPath (Join-Path $fixtureScripts 'native-paths.ps1')) { (Get-FileHash -LiteralPath (Join-Path $fixtureScripts 'native-paths.ps1')).Hash.ToLowerInvariant() } else { $null }
        }
        checks = $checks
        passed = -not $failureType -and @($checks.Values | Where-Object { $_ -ne $true }).Count -eq 0
        failure_type = $failureType
    }
    $null = New-Item -ItemType Directory -Path (Split-Path -Parent $outputFullPath) -Force
    $evidence | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $outputFullPath -Encoding UTF8
}
if (-not $evidence.passed) { throw "Native supervisor validation failed ($failureType). Inspect the isolated fixture logs." }
Write-Output "Native supervisor validation passed: $($checks.Count) checks. Evidence: $outputFullPath"
