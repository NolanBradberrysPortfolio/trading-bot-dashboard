# Dashboard Audit Fix Log

Generated: 2026-05-27 America/Los_Angeles

## Scope

Reviewed the public trading dashboard, Polymarket paper ledgers, stock/crypto local paper runner, dashboard exporter, refresh/publish scripts, and deployed-data workflow assumptions.

## Agents Used

- Raman: trading/execution audit across strategies, ledgers, paper runner, refresh scripts, and data reconciliation.
- Bernoulli: adversarial dashboard/UI/data audit of the public site and local static files.
- Ohm: second adversarial pass against the fixed version. Status: running at time of initial log creation.
- Ohm completed a second adversarial pass and found six additional issues; all six were addressed or resolved by publishing workflow below.

## Fixes Applied

1. Export all public Polymarket open positions instead of truncating each strategy to 12 rows.
   - Added `positions_exported` and `positions_truncated` fields.
   - Verified `open_positions` now equals exported position rows for every Polymarket strategy.

2. Made Polymarket mark handling safer.
   - If mark fetching fails, positions are carried at cost instead of silently showing zero value.
   - Missing individual quotes now carry at cost with a warning.
   - Bundle bid/mid marks now subtract modeled exit fees.
   - Export now includes `missing_mark_count` and row-level mark warnings.

3. Fixed Polymarket settlement edge case.
   - A missing `winner_index` no longer counts as a winning NO leg or resolved single position.

4. Improved stock/crypto paper accounting.
   - Future runner state now tracks cost basis, average entry, and realized PnL.
   - Dashboard export derives position cost basis and unrealized PnL from order history.
   - Quant `closed_positions` now counts exit orders instead of all orders.
   - Added `orders_count` and explicit execution model labels.

5. Cleaned stock/crypto daily marks.
   - Runner now upserts one mark row per calendar date.
   - Existing duplicate `2026-05-22` mark rows were collapsed to one row.

6. Removed misleading public operational details.
   - Public JSON suppresses stock/crypto broker notes.
   - Public security text now states that market names, sides, prices, and paper sizes are still visible.

7. Fixed dashboard UI behavior.
   - Search now updates summary totals, strategy count, allocation chart, cards, and open trades.
   - `Needs Attention` now includes strategies with losing/warning/past-end open rows.
   - Null bid/ask fields render as `N/A` instead of crashing or displaying fake zeros.
   - JSON-rendered strings are escaped before insertion into HTML.
   - Small nonzero returns no longer round to a misleading `+0.0%`.
   - Crypto strategies holding BIL now label it as a fallback cash/T-bill sleeve.
   - Strategy cards show execution-model limitations.

8. Hardened refresh execution.
   - Daily refresh script now uses an exclusive lock to avoid overlapping runs.
   - Dashboard JSON, Polymarket state, and quant account writes are atomic.

9. Fixed second-pass quant reconciliation issue.
   - Stock/crypto cost basis is reconstructed from `orders.csv` before export.
   - The local paper runner backfills account cost basis and realized PnL from order history before each rebalance.
   - Verified each stock/crypto strategy now satisfies `total_bid_pnl = realized_pnl + unrealized_bid_pnl`.

10. Fixed bundle row display.
    - Negative-risk bundle rows now export an aggregate entry cost per bundle.
    - Bundle rows now expose aggregate `bundle bid / mid` marks instead of blank bid/ask fields.

11. Fixed empty-search and refresh-click edge cases.
    - Empty strategy filters now show `$0` in the allocation chart instead of `$1`.
    - The frontend refresh button is disabled while a data fetch is already in flight.

12. Locked the alternate local refresh path.
    - `refresh_dashboard.ps1` now uses the same lock file as `refresh_and_publish.ps1`.

## Verification

- `python -m py_compile trading-dashboard/export_dashboard_data.py`: passed.
- `python -m py_compile polymarket_multi_paper_trader.py`: passed.
- `python -m py_compile quant_strategy_screen/forward_test/local_paper_runner.py`: passed.
- `node --check trading-dashboard/public/app.js`: passed.
- Ran stock/crypto local paper runner: passed with 8 orders, 0 errors.
- Ran Polymarket multi paper trader: passed with 10,000 markets fetched.
- Ran Polymarket single paper trader: passed with 6,000 markets fetched.
- Regenerated `public/data/dashboard-data.json`: 24 strategies exported.
- Data audit: 29 checks passed, 0 failed.
- UI simulation audit: search-aware summaries, escaping, null bid/ask, fallback labels, and execution labels passed.
- Static HTTP checks on local server: `/`, `/app.js`, and `/data/dashboard-data.json` returned HTTP 200.
- Second-pass data audit: 0 reconciliation issues across 24 strategies and 83 exported positions.
- Second-pass UI simulation: empty-search summary, empty-search donut label, locked refresh, null ask, bundle mark prefix, and no `undefined` rendering all passed.
- PowerShell parser check: `refresh_dashboard.ps1` and `refresh_and_publish.ps1` passed.

## Residual Design Limitations

- Polymarket paper fills still do not simulate full order-book depth. The dashboard now labels this explicitly.
- Stock/crypto paper fills are daily close-model paper fills, not broker-routed real fills. The dashboard now labels this explicitly.
- GitHub Pages remains public. `robots.txt` is not access control; use Cloudflare Access for private sharing.
