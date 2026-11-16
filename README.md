# Hong Kong property index tracker

One pipeline collects three Hong Kong residential price indices, writes them to SQLite, and opens a bilingual dashboard.

The Centa-City Leading Index uses a fixed Centanet history API, then a weekly Playwright check against the live page. The Rating and Valuation Department Private Domestic Price Index and the Midland Realty Property Price Index go through Tavily, then Firecrawl. If Tavily has no key or returns nothing useful, the run continues from the official seed URL and records that fallback. Playwright is used for those two sites only when Firecrawl fails the quality gate. After the readings are stored, Ollama Cloud writes a short comparison in English and Traditional Chinese.

## What you get

- Full weekly Centa-City Leading Index history, from the Centanet chart API `https://hk.centanet.com/CCI/api/Index/CCLChart`
- A weekly update of the three latest points, read on `https://hk.centanet.com/CCI/index` and accepted only when the chart matches the on-page headline
- The latest Rating and Valuation Department Private Domestic Price Index (All Classes), checked against the official monthly file, plus that full monthly series for download
- The latest Midland Realty Property Price Index from the official market-insight page
- `output.md` and the dashboard both show the Ollama Cloud comparison
- Download buttons for each series currently stored in SQLite
- A language switch between English and Traditional Chinese

The dashboard uses the full names: Centa-City Leading Index, Rating and Valuation Department Private Domestic Price Index, and Midland Realty Property Price Index.

## Project layout

| Path | Role |
| --- | --- |
| `schema.sql` | SQLite tables |
| `app/ccl_history.py` | Centa-City Leading Index history load |
| `app/ccl_weekly.py` | Weekly Playwright update |
| `app/adaptive.py` | Tavily, Firecrawl, and Playwright fallback |
| `app/insight.py` | Ollama Cloud insight |
| `app/pipeline.py` | Runs every step |
| `app/dashboard.py` | Local dashboard |
| `output.md` | Latest insight, written by the pipeline |
| `evidence/` | JSON record of each successful path |
| `data/indices.sqlite` | Local database |

## Requirements

- Python 3.11 or newer
- Network access to Centanet, the Rating and Valuation Department, Midland Realty, Tavily, Firecrawl, and Ollama Cloud
- Chromium for Playwright

Copy `.env.example` to `.env` and fill in:

```
OLLAMA_API_KEY=
OLLAMA_MODEL=kimi-k3.1-pro
TAVILY_API_KEY=
FIRECRAWL_API_KEY=
```

`TAVILY_API_KEY` can be left empty. The adaptive steps then log a seed-URL fallback and continue with Firecrawl. `OLLAMA_API_KEY` is required for the insight. The model endpoint is `https://ollama.com/v1/chat/completions`.

## Linux

```bash
cd hong-kong-property-index-tracker
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m playwright install --with-deps chromium
cp .env.example .env
```

Edit `.env`, then:

```bash
python -m app.pipeline
python -m app.dashboard
```

Open `http://127.0.0.1:5050`.

`playwright install --with-deps` installs system libraries and may ask for sudo. On a server where you cannot install system packages, install Chromium's dependencies yourself and run `python -m playwright install chromium`.

## Windows

Use PowerShell.

```powershell
cd hong-kong-property-index-tracker
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m playwright install chromium
copy .env.example .env
```

Edit `.env`, then:

```powershell
python -m app.pipeline
python -m app.dashboard
```

Open `http://127.0.0.1:5050`.

If script execution is disabled, run `Set-ExecutionPolicy -Scope Process RemoteSigned` before activating the virtual environment. CSV downloads include a UTF-8 BOM so Excel shows the Traditional Chinese series name correctly.

## Run one step

From the project root, with the virtual environment active:

```bash
python -m app.ccl_history
python -m app.ccl_weekly
python -m app.adaptive
python -m app.insight
python -m app.dashboard
```

`python -m app.pipeline` runs them in that order. The insight step needs all three latest readings.

## Quality gates

A reading is not written when the gate fails.

- Centa-City Leading Index history must contain the weekly series back to 1994, with a 7-day gap, and a latest week within the last 21 days.
- The weekly page update reads the `本週公佈` value and the `反映…至…` date, then keeps the three newest chart points only when the newest value and date match that headline.
- The Rating and Valuation Department extraction must match the latest All Classes figure in the official monthly file, within 0.5 points and the same month.
- The Midland Realty extraction must be a territory-wide index point in a plausible range, with an as-of date in the last 21 days. Prices per square foot and district sub-indices are rejected.

## Tavily fallback

Tavily is optional. When `TAVILY_API_KEY` is missing, Tavily returns no official URL, or the request fails, the pipeline logs a seed-URL fallback and continues:

- Rating and Valuation Department: `https://www.rvd.gov.hk/en/publications/property_market_statistics.html`, then the monthly file `https://www.rvd.gov.hk/datagovhk/1.4M.csv` if the page extract does not pass the gate
- Midland Realty: `https://www.midland.com.hk/en/market-insight/`

Playwright runs only after those Firecrawl attempts fail. The path log in SQLite and the evidence section on the dashboard record which path succeeded.

## Dashboard

The page shows a history chart for each stored series — the Centa-City Leading Index, the Rating and Valuation Department Private Domestic Price Index, and the Midland Realty Property Price Index — plus the latest value of each index under its full name, a download for each stored series, and the insight in the selected language. Weekly charts label dates as YYYY-MM-DD. The monthly chart labels months as YYYY-MM. A short series draws a point on every reading, and a series with no stored points shows an empty state instead of a chart. The English / 繁體中文 control changes labels, buttons, series names, chart titles, and the insight. The choice is remembered in the browser.

These series do not share a base period. The Centa-City Leading Index is July 1997 = 100. The Rating and Valuation Department index is 1999 = 100. The levels are shown as published.

## Deployment

Live deployment notes and the git history for the class report are in [docs/deployment-log.md](docs/deployment-log.md).
