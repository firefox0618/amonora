Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$LocalRoot = "C:\Ops\Backups\amonora"
$KeyPath = "C:\Users\Skyfal\.ssh\id_ed25519"
$ScpPath = "C:\Windows\System32\OpenSSH\scp.exe"

$Nodes = @(
    @{
        Name = "vpn-de"
        HostIp = "213.108.20.34"
    }
)

$Date = Get-Date -Format "yyyy-MM-dd_HH-mm"

if (-not (Test-Path $ScpPath)) {
    throw "scp.exe not found at $ScpPath"
}

if (-not (Test-Path $KeyPath)) {
    throw "SSH key not found at $KeyPath"
}

foreach ($Node in $Nodes) {
    $NodeName = $Node.Name
    $HostIp = $Node.HostIp
    $NodeBase = Join-Path $LocalRoot $NodeName
    $Dest = Join-Path $NodeBase $Date

    New-Item -ItemType Directory -Path $Dest -Force | Out-Null

    $DbRemoteSpec = "root@${HostIp}:/opt/3x-ui/db/x-ui.db"
    $BackupsRemoteSpec = "root@${HostIp}:/opt/3x-ui/backups/*"

    Write-Host ""
    Write-Host "Copying live x-ui.db from $HostIp"
    Write-Host "Destination: $Dest"
    & $ScpPath -i $KeyPath $DbRemoteSpec $Dest

    $ExitCodeVar = Get-Variable -Name LASTEXITCODE -Scope Global -ErrorAction SilentlyContinue
    if ($ExitCodeVar -and $ExitCodeVar.Value -ne 0) {
        throw "scp failed while copying x-ui.db from $HostIp with exit code $($ExitCodeVar.Value)"
    }

    Write-Host "Copying backup artifacts from $HostIp"
    & $ScpPath -i $KeyPath $BackupsRemoteSpec $Dest

    $ExitCodeVar = Get-Variable -Name LASTEXITCODE -Scope Global -ErrorAction SilentlyContinue
    if ($ExitCodeVar -and $ExitCodeVar.Value -ne 0) {
        throw "scp failed while copying backup artifacts from $HostIp with exit code $($ExitCodeVar.Value)"
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
    Write-Host "Copied files for ${NodeName}:"
    $Files |
        Select-Object Name, Length, LastWriteTime |
        Format-Table -AutoSize
}

Write-Host ""
Write-Host "Applying retention policy for local VPN node backups..."

$Threshold = (Get-Date).AddDays(-7)

foreach ($Node in $Nodes) {
    $NodeBase = Join-Path $LocalRoot $Node.Name
    if (-not (Test-Path $NodeBase)) {
        continue
    }

    Get-ChildItem -Path $NodeBase -Directory | ForEach-Object {
        if ($_.LastWriteTime -lt $Threshold) {
            Write-Host "Removing old backup folder: $($_.FullName)"
            Remove-Item -Recurse -Force $_.FullName
        }
    }
}
