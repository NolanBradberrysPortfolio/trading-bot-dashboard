# Deployment

## Recommended: Cloudflare Pages + Cloudflare Access

This is the cheapest option that still gives real access control.

1. Push this folder to a GitHub repository.
2. In Cloudflare Pages, create a new project from that repository.
3. Use these build settings:
   - Framework preset: `None`
   - Build command: empty
   - Build output directory: `public`
4. In Cloudflare Zero Trust, add an Access application for the Pages hostname.
5. Add allowed emails or an identity provider policy.

Cloudflare Pages is free for static hosting. Cloudflare Access has a free plan for small teams. Verify the current limits in Cloudflare before publishing anything sensitive.

### Cloudflare CLI

If the local machine is logged in with Wrangler, deploy directly:

```powershell
npx wrangler pages deploy public --project-name trading-bot-dashboard
```

For GitHub Actions, add these repository secrets:

```text
CLOUDFLARE_API_TOKEN
CLOUDFLARE_ACCOUNT_ID
```

Then copy `cloudflare-pages.workflow.example.yml` to `.github/workflows/cloudflare-pages.yml`.

## Public Option: GitHub Pages

Use this only for public-safe summaries.

1. Commit `trading-dashboard/public`.
2. Publish the static files to the `gh-pages` branch:

```powershell
.\publish_github_pages.ps1
```

3. Enable GitHub Pages with `gh-pages` / root as the source.

GitHub Pages is cheap/free but does not protect the page from public visitors. Do not publish private strategy positions there unless you are comfortable with anyone seeing them.

## Refresh Data Before Deploy

Run:

```powershell
python .\trading-dashboard\export_dashboard_data.py
```

Or refresh the trading ledgers first:

```powershell
.\trading-dashboard\refresh_dashboard.ps1
```

That updates:

```text
trading-dashboard/public/data/dashboard-data.json
```

To refresh and republish GitHub Pages in one command:

```powershell
.\trading-dashboard\refresh_and_publish.ps1
```

## Automation Option

The existing Codex automation can be extended to run this after the paper traders:

```powershell
python trading-dashboard/export_dashboard_data.py
```

If deployed through GitHub, add a follow-up step that commits and pushes only the static dashboard data. Do not commit `.env`, broker credentials, API keys, or raw state files.
