$ErrorActionPreference = "Stop"

$DashboardRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$LockPath = Join-Path $DashboardRoot "logs\refresh.lock"
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $LockPath) | Out-Null
$LockStream = $null
try {
    $LockStream = [System.IO.File]::Open($LockPath, [System.IO.FileMode]::OpenOrCreate, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
}
catch {
    Write-Output "Another dashboard refresh is already running. Exiting without changes."
    exit 0
}

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

try {
    python .\polymarket_paper_trader.py run
    python .\polymarket_multi_paper_trader.py run
    python ..\there-s-an-openclaw-instance-called\quant_strategy_screen\forward_test\local_paper_runner.py
    python .\trading-dashboard\export_dashboard_data.py

    Write-Host "Dashboard data refreshed: trading-dashboard/public/data/dashboard-data.json"
}
finally {
    if ($LockStream) {
        $LockStream.Close()
        $LockStream.Dispose()
    }
}
