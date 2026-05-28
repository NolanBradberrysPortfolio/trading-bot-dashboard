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
Push-Location $DashboardRoot
try {
    $WorkspaceRoot = Split-Path -Parent $DashboardRoot
    $PolymarketSingle = Join-Path $WorkspaceRoot "polymarket_paper_trader.py"
    $PolymarketMulti = Join-Path $WorkspaceRoot "polymarket_multi_paper_trader.py"
    if (Test-Path $PolymarketSingle) {
        python $PolymarketSingle run
    }
    if (Test-Path $PolymarketMulti) {
        python $PolymarketMulti run
    }

    $QuantRunner = Join-Path (Split-Path -Parent (Split-Path -Parent $DashboardRoot)) "there-s-an-openclaw-instance-called\quant_strategy_screen\forward_test\local_paper_runner.py"
    if (Test-Path $QuantRunner) {
        python $QuantRunner
    }

    python .\export_dashboard_data.py

    git checkout main
    git add public\data\dashboard-data.json
    git diff --cached --quiet
    if ($LASTEXITCODE -ne 0) {
        git commit -m "Refresh dashboard data"
        git push origin main
    }

    .\publish_github_pages.ps1

    if ($env:CLOUDFLARE_API_TOKEN -and $env:CLOUDFLARE_ACCOUNT_ID) {
        npx wrangler pages deploy public --project-name trading-bot-dashboard
    }
    else {
        Write-Output "Skipping Cloudflare deploy: CLOUDFLARE_API_TOKEN and/or CLOUDFLARE_ACCOUNT_ID are not set."
    }
}
finally {
    Pop-Location
    if ($LockStream) {
        $LockStream.Close()
        $LockStream.Dispose()
    }
}
