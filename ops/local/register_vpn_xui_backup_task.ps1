Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$TaskName = "Amonora VPN XUI Backup Daily"
$RunAt = "09:15"
$WindowsScriptDir = "C:\Users\Skyfal\Scripts\amonora"
$WindowsScriptPath = Join-Path $WindowsScriptDir "backup_vpn_xui_artifacts.ps1"
$SourceScriptPath = "C:\Users\Skyfal\Downloads\backup_vpn_xui_artifacts.ps1"
$PowerShellPath = "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"

if (-not (Test-Path $PowerShellPath)) {
    throw "PowerShell executable not found at $PowerShellPath"
}

if (-not (Test-Path $SourceScriptPath)) {
    throw "Source VPN backup script not found at $SourceScriptPath"
}

New-Item -ItemType Directory -Path $WindowsScriptDir -Force | Out-Null
Copy-Item -Path $SourceScriptPath -Destination $WindowsScriptPath -Force

$Action = New-ScheduledTaskAction -Execute $PowerShellPath -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$WindowsScriptPath`""
$Trigger = New-ScheduledTaskTrigger -Daily -At $RunAt
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -StartWhenAvailable

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Principal $Principal `
    -Settings $Settings `
    -Force | Out-Null

Write-Host "Scheduled task registered:"
Write-Host "  Name: $TaskName"
Write-Host "  Time: daily at $RunAt"
Write-Host "  Script: $WindowsScriptPath"
