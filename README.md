# Trading Bot Monitor

Static dashboard for the current Codex trading-bot workspaces.

It exports a sanitized JSON snapshot and renders it with a plain HTML/CSS/JS frontend. There are no trading controls in the site.

## Data Sources

- Polymarket paper traders in `../paper_trading_multi_state.json`
- Polymarket single favorite paper trader in `../paper_trading_state.json` is intentionally not double-counted because it duplicates `favorite_14d_broad`
- Stock/crypto local paper account in `../../there-s-an-openclaw-instance-called/quant_strategy_screen/forward_test/local_paper_account.json`

## Refresh Locally

```powershell
python .\trading-dashboard\export_dashboard_data.py
```

To run the paper traders first and then export the dashboard:

```powershell
.\trading-dashboard\refresh_dashboard.ps1
```

Then serve the static site:

```powershell
python -m http.server 8765 -d .\trading-dashboard\public
```

Open:

```text
http://localhost:8765
```

## Security Model

The default export is public-safe:

- no API keys
- no broker credentials
- no wallet addresses
- no CLOB token IDs
- no trading buttons
- no order execution endpoints

Open positions are still visible as market names and sides. If that is too much information for a public page, remove `positions` in `export_dashboard_data.py` or deploy behind Cloudflare Access.

## Cheapest Secure Sharing

Recommended: Cloudflare Pages plus Cloudflare Access.

- Cloudflare Pages free tier is enough for this static dashboard.
- Cloudflare Access can protect the URL with login/email allow lists for small groups.
- GitHub Pages is fine for a public summary, but not for sensitive live/paper positions because it does not add real visitor authentication to a public site.

See `DEPLOYMENT.md`.

## Static Hosting

This folder is now self-contained for static hosting:

- `public/` is the site output.
- `publish_github_pages.ps1` publishes `public/` to the repo's `gh-pages` branch.
- `wrangler.toml` is ready for Cloudflare Pages.
- `cloudflare-pages.workflow.example.yml` is a GitHub Actions template for Cloudflare once the repo has a token with workflow scope.
- `public/robots.txt` discourages indexing, but it is not access control.
