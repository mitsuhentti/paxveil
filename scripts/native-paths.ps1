function Get-PaxveilBackupDirectory([string]$RepoPath, [string]$RuntimePath) {
    if ($RuntimePath.Equals($RepoPath, [StringComparison]::OrdinalIgnoreCase) -or $RuntimePath.StartsWith($RepoPath + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        return Join-Path (Split-Path -Parent $RepoPath) 'paxveil-private-backups'
    }
    return Join-Path $RuntimePath 'backups'
}
