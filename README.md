# ECHO · Seasonality, tested

Static website: seasonal charts for 66 markets with statistical tests, a cross-market screener, event impact (FOMC, NFP, CBRT), COT positioning, policy rates, inflation and market hours.

## How it works

| Part | File |
|---|---|
| Page (loads `data/*.json` at runtime) | `scripts/template.html` → built to `index.html` by `scripts/build_site.py` |
| Market list, data cleaning, start dates | `scripts/universe.py` |
| Price download (Yahoo Finance) | `scripts/fetch_prices.py` |
| Seasonality, tests, Benjamini-Hochberg | `scripts/compute.py` |
| COT (CFTC), rates and CPI (BIS), upcoming events, outlook | `scripts/tools.py` |
| Data audit (coverage, gaps, stale prices, outliers) | `scripts/audit.py` |
| Daily pipeline with validation | `scripts/update.py` |
| Daily bot | `.github/workflows/update.yml` |

No API keys or accounts are needed: every source is public (Yahoo Finance, CFTC, BIS, Federal Reserve, CBRT).

## Daily bot

`.github/workflows/update.yml` runs on this schedule (and on every push, or by hand from the Actions tab):

| When | What changes |
|---|---|
| Every day 22:30 UTC (after the US close; weekends too, for crypto) | prices, the running-year line, today's marker, year-to-date figures, "from today" outlook, rates and inflation when the BIS publishes, event calendars |
| Fridays 20:50 UTC (right after the CFTC release at 15:30 New York) | COT report. If a holiday moves the release, the daily run picks it up |
| Once a year, on the first run of January | averages and tests roll forward: the year that just ended joins the 2Y–20Y lines, the screener and every statistic |

Every run:

1. refreshes the FOMC and CBRT calendars,
2. downloads full daily history for all 66 markets,
3. recomputes every chart and test, the COT report, rates, inflation and the 30-day outlook,
4. validates the result (market counts, no older data than before). If any check fails, the job fails and the previous site stays online,
5. publishes the page to GitHub Pages,
6. on the 1st and 15th of each month commits a small `status.json`, because GitHub pauses scheduled workflows in public repositories after 60 days without commits.

The full run takes about 10 minutes (downloads ~3 min, statistics ~6 min).

Averages and tests use completed calendar years only. The running year is drawn separately (its line is named after the year, e.g. 2026) and shown under each month card; the seasonal chart marks today with a dashed line and a dot on each average line.

## Launch checklist

1. Create a GitHub repository and push this folder (`git init && git add . && git commit -m "ECHO" && git push`).
2. Repository **Settings → Pages → Source: GitHub Actions**.
3. **Actions** tab → *Daily data update* → **Run workflow** once. The site appears at `https://<user>.github.io/<repo>/`.
4. Set `SITE_URL` in `scripts/build_site.py` to the real address (`https://<user>.github.io/<repo>/` or your domain) so link previews show the logo. Custom domain: Settings → Pages → Custom domain.
5. If a daily run fails (for example Yahoo Finance briefly blocks the download), the site keeps the previous day's data; the next run fixes it. Failed runs are listed in the Actions tab and GitHub emails the repository owner.
6. Before going public: legal review of the Terms / Privacy / Risk texts, and check Yahoo Finance's terms for commercial use (a licensed data feed may be needed).

## Local run

```bash
pip install -r requirements.txt
python scripts/build_site.py _site
python scripts/update.py _site
cd _site && python -m http.server 8000   # open http://localhost:8000
```
