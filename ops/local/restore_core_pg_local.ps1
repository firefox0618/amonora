param(
    [switch]$KeepContainer
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$WslPath = "C:\Windows\System32\wsl.exe"
$RepoPath = "/home/dextrmed/projects/amonora_bot"
$ScriptPath = "./ops/local/restore_core_pg_local.sh"

if (-not (Test-Path $WslPath)) {
    throw "wsl.exe not found at $WslPath"
}

$Arguments = @(
    "bash",
    "-lc",
    "cd $RepoPath && $ScriptPath" + ($(if ($KeepContainer) { " --keep-container" } else { "" }))
)

& $WslPath @Arguments
$ExitCodeVariable = Get-Variable -Name LASTEXITCODE -Scope Global -ErrorAction SilentlyContinue
$ExitCode = if ($ExitCodeVariable) { $ExitCodeVariable.Value } else { 0 }

if ($ExitCode -ne 0) {
    throw "WSL restore script failed with exit code $ExitCode"
}
