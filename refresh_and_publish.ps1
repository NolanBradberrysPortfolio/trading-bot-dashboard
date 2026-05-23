$ErrorActionPreference = "Stop"

$DashboardRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $DashboardRoot
try {
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
}
