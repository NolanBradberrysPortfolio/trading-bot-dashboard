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
}
finally {
    Pop-Location
}
