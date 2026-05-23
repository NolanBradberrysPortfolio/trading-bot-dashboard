$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

python .\polymarket_paper_trader.py run
python .\polymarket_multi_paper_trader.py run
python ..\there-s-an-openclaw-instance-called\quant_strategy_screen\forward_test\local_paper_runner.py
python .\trading-dashboard\export_dashboard_data.py

Write-Host "Dashboard data refreshed: trading-dashboard/public/data/dashboard-data.json"
