$ErrorActionPreference = "Stop"

$DashboardRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogDir = Join-Path $DashboardRoot "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$LogPath = Join-Path $LogDir "daily-update-$Stamp.log"

Start-Transcript -Path $LogPath -Append | Out-Null
try {
    Write-Output "Starting trading dashboard daily update at $(Get-Date -Format o)"
    & (Join-Path $DashboardRoot "refresh_and_publish.ps1")
    Write-Output "Finished trading dashboard daily update at $(Get-Date -Format o)"
}
finally {
    Stop-Transcript | Out-Null
}
