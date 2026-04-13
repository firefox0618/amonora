Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$HostIp = "46.21.81.186"
$RemotePath = "/opt/amonora_bot/backups/pg"
$LocalRoot = "C:\Ops\Backups\amonora"
$LocalBase = Join-Path $LocalRoot "core-pg"
$KeyPath = "C:\Users\Skyfal\.ssh\id_ed25519"
$ScpPath = "C:\Windows\System32\OpenSSH\scp.exe"
$RclonePath = "C:\Tools\rclone\rclone.exe"
$RcloneRemote = "amonora-backup:core-pg"

$Date = Get-Date -Format "yyyy-MM-dd_HH-mm"
$Dest = Join-Path $LocalBase $Date

if (-not (Test-Path $ScpPath)) {
    throw "scp.exe not found at $ScpPath"
}

if (-not (Test-Path $KeyPath)) {
    throw "SSH key not found at $KeyPath"
}

New-Item -ItemType Directory -Path $Dest -Force | Out-Null

$RemoteSpec = "root@${HostIp}:${RemotePath}/*.sql.gz"

Write-Host "Copying PostgreSQL dump(s) from $RemoteSpec"
Write-Host "Destination: $Dest"

& $ScpPath -i $KeyPath $RemoteSpec $Dest

$ExitCodeVar = Get-Variable -Name LASTEXITCODE -Scope Global -ErrorAction SilentlyContinue

if ($ExitCodeVar -and $ExitCodeVar.Value -ne 0) {
    throw "scp failed with exit code $($ExitCodeVar.Value)"
}

Start-Sleep -Milliseconds 500
$Files = @()
for ($Attempt = 1; $Attempt -le 5; $Attempt++) {
    $Files = @(Get-ChildItem -File $Dest)
    $HasZeroSize = $Files | Where-Object { $_.Length -eq 0 }
    if ($Files.Count -gt 0 -and -not $HasZeroSize) {
        break
    }
    Start-Sleep -Seconds 2
}

if (-not $Files) {
    throw "No files were copied to $Dest"
}

Write-Host ""
Write-Host "Backup copied successfully:"
$Files |
    Select-Object Name, Length, LastWriteTime |
    Format-Table -AutoSize

Write-Host ""
Write-Host "Applying retention policy for local core PostgreSQL backups..."

$BackupRoot = $LocalBase
$Threshold = (Get-Date).AddDays(-7)

Get-ChildItem -Path $BackupRoot -Directory | ForEach-Object {
    if ($_.LastWriteTime -lt $Threshold) {
        Write-Host "Removing old backup folder: $($_.FullName)"
        Remove-Item -Recurse -Force $_.FullName
    }
}

Write-Host ""
Write-Host "Checking optional cloud upload step..."

if (-not (Test-Path $RclonePath)) {
    Write-Host "rclone not found at $RclonePath - skipping upload"
    return
}

$RcloneExit = $null
$ConfiguredRemotes = & $RclonePath listremotes
$RcloneExitVar = Get-Variable -Name LASTEXITCODE -Scope Global -ErrorAction SilentlyContinue
if ($RcloneExitVar) {
    $RcloneExit = $RcloneExitVar.Value
}

if ($RcloneExit -ne $null -and $RcloneExit -ne 0) {
    Write-Host "rclone remotes could not be listed - skipping upload"
    return
}

if ($ConfiguredRemotes -notcontains "amonora-backup:") {
    Write-Host "Remote amonora-backup: is not configured yet - skipping upload"
    return
}

Write-Host "Uploading backups to $RcloneRemote ..."
& $RclonePath copy $BackupRoot $RcloneRemote --progress --transfers=2 --checkers=2

$RcloneCopyExit = $null
$RcloneCopyExitVar = Get-Variable -Name LASTEXITCODE -Scope Global -ErrorAction SilentlyContinue
if ($RcloneCopyExitVar) {
    $RcloneCopyExit = $RcloneCopyExitVar.Value
}

if ($RcloneCopyExit -ne $null -and $RcloneCopyExit -ne 0) {
    throw "rclone copy failed with exit code $RcloneCopyExit"
}

Write-Host "Cloud upload completed successfully."
