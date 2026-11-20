# Manifest – hong-kong-property-index-tracker

## Repository Name
`hong-kong-property-index-tracker`

## Goal
Build one system that:
1. **Centa-City Leading Index (deterministic path)**: Fetch full historical series via the Centanet history API into local SQL. Weekly use Playwright with stable pattern matching to upsert the three latest points.
2. **Rating and Valuation Department Private Domestic Price Index + Midland Property Price Index (adaptive path)**: Use Tavily → Firecrawl (with optional Playwright fallback) to extract the latest values. Store or display them alongside the Centa-City Leading Index. Midland must stay one series: the territory-wide weekly All / 全港 index. Refuse a reading from a different Midland series. When that official series is confirmed, replace the stored Midland rows with the published weekly history.
3. After data is stored, **must** generate a short natural-language insight using Ollama Cloud that compares the latest values of the three indices.
4. Provide a live dashboard that shows a separate history chart for each of the three indices, latest values (with full index names), download buttons for each full dataset, and the Ollama-generated insight. The three series use different base periods, so the charts stay separate. The page title is `Hong Kong property indices · Dominic Yu` in English and `香港樓價指數 · Dominic Yu` in Traditional Chinese. The eyebrow above the title is `One site with patterns, many sites with Firecrawl` / `單一網站靠規律，多個網站靠 Firecrawl`. Each latest-reading card shows the full name, the latest value, the as-of date, the base period, the percent change versus the previous reading (up or down), a provisional badge when the reading is provisional, how many readings are stored, a source/path label, and the download button. The dashboard includes a Collection evidence / 採集紀錄 section that lists the twelve most recent collection-path logs with success, fallback, or fail status. Evidence is not only an off-page log file.
5. The dashboard UI must support switching between **English** and **Traditional Chinese**. Persist the choice in localStorage under `hk-index-lang`.
6. README with full Windows + Linux setup instructions.

## Core Principle for Storytelling
Pure pattern-based scraping (hard-coded selectors) works well for **one** known site (Centa-City Leading Index), but breaks when the site changes and cannot easily be reused.  
By adding Tavily + Firecrawl, the same pipeline can reliably extract from **multiple** similar property indices (Rating and Valuation Department and Midland) without writing new selectors for each one.  
After collection, Ollama Cloud turns the numbers into a readable insight.

## Official Targets
- **Centa-City Leading Index**: `https://hk.centanet.com/CCI/index` + Centanet history API
- **Rating and Valuation Department Private Domestic Price Index**: official RVD pages / data.gov.hk Excel
- **Midland Property Price Index**: `https://www.midland.com.hk/en/market-insight/` — the territory-wide weekly All / 全港 figure (美聯樓價指數), published as `mrIndexWeekly[].mr_index`. District indices, the confidence index, and other figures on that page are different series.

## Required Project Files
- `.env.example` with:
  ```
  OLLAMA_API_KEY=
  TAVILY_API_KEY=
  FIRECRAWL_API_KEY=
  ```
- Scripts for: Centa-City Leading Index history load + weekly update, Rating and Valuation Department / Midland extraction, insight generation, dashboard
- SQL schema
- `README.md` (Windows + Linux server setup)

## Pipeline Design
### 1. Centa-City Leading Index – Deterministic
- Full history: call Centanet history API → store in local SQL (SQLite).
- Weekly: Playwright with explicit, stable selectors / pattern matching to extract the three latest weekly points → upsert to SQL.
- Quality gate required before writing.

### 2. Rating and Valuation Department + Midland – Adaptive (Tavily + Firecrawl)
- **Tavily is preferred but optional.** If `TAVILY_API_KEY` is set, use Tavily first to discover or confirm the current official page URL. This allows recovery even if the original URL changes.
- If `TAVILY_API_KEY` is missing or Tavily fails, fall back to the hard-coded official seed URL and continue with Firecrawl.
- Log clearly when the seed-URL fallback is used.
- Use Firecrawl to extract the latest index value and date in structured form.
- Fall back to Playwright only if Firecrawl fails the quality check.
- Store the latest values in SQL or display them on the dashboard latest-reading cards.
- Log which path succeeded.
- **Midland stays one official series.** Tavily can still discover or confirm a Midland URL, but check `https://www.midland.com.hk/en/market-insight/` before accepting a reading, including when Tavily returns another Midland URL. That page is not replaced by a different Midland URL. Keep only the territory-wide weekly Midland Property Price Index (美聯樓價指數): the All / 全港 figure published as `mrIndexWeekly[].mr_index`.
- District indices, the confidence index, and any other figure on that page must not be written into the Midland series.
- A newly extracted Midland reading that is incompatible with the stored official series must be refused, not silently upserted. Incompatible means a clearly different series name or scope, or a large level gap from the stored series. The mixed chart was All / 全港 readings around 148–149 beside another cluster around 110, about 38 points apart. A reading more than 8 points from the stored official level is incompatible.
- A confirmed official Midland run replaces the Midland rows with the published weekly history, so a wrong cluster cannot remain.
- Midland values already in SQL are a full downloadable history, not only a latest point.

### 3. Required Ollama Cloud Insight
After the latest data is stored, the system **must** call Ollama Cloud (via `OLLAMA_API_KEY` at `https://ollama.com/v1`) to generate a short natural-language insight that compares the latest values of the Centa-City Leading Index, Rating and Valuation Department Private Domestic Price Index, and Midland Property Price Index.  
The insight must be:
- Saved (e.g. in `output.md` or a database field)
- Displayed on the live dashboard
- Available in both English and Traditional Chinese (or generated in the currently selected language)

### 4. Dashboard
- Use **full index names** everywhere (not abbreviations):
  - Centa-City Leading Index (not CCL)
  - Rating and Valuation Department Private Domestic Price Index (not RVD)
  - Midland Property Price Index (not Midland)
- A separate history chart for each index. Do not plot the three series on one shared scale; their base periods differ.
  - Centa-City Leading Index: weekly, the long series, dates as YYYY-MM-DD
  - Rating and Valuation Department Private Domestic Price Index: monthly, labels as YYYY-MM
  - Midland Realty Property Price Index: weekly. A short series still draws a point for each reading.
- An empty series shows an empty state and leaves the other charts in place.
- Chart titles and labels follow the language switcher.
- Latest values of all three indices side-by-side
- **Download buttons**: Users must be able to download the full dataset for each index (CSV or Excel) directly from the dashboard. The Midland download is the full weekly history already in SQL, not only the latest point.
- The Ollama-generated comparison insight
- **Language switcher**: A clear control to switch the entire UI between English and Traditional Chinese.
- **Weekly AI update notice**: A clearly visible line, shown without scrolling past the title, that switches with the language control:
  - English: `Data is fetched, processed, and updated by AI automatically every week.`
  - Traditional Chinese: `數據由 AI 每週自動擷取、處理並更新。`
- **Author**: Show Dominic Yu and dominic@data-science-hk.org on the dashboard.
- **Page title**: `Hong Kong property indices · Dominic Yu` in English and `香港樓價指數 · Dominic Yu` in Traditional Chinese. Use it as the document title and the page heading. It switches with the language control.
- **Eyebrow**: Above the title, `One site with patterns, many sites with Firecrawl` in English and `單一網站靠規律，多個網站靠 Firecrawl` in Traditional Chinese.
- **Latest-reading cards**: One card per index. Each card shows the full name, the latest value, the as-of date, the base period, the percent change versus the previous reading (up or down), a provisional badge when the reading is provisional, how many readings are stored, a source/path label, and the download button for the full dataset.
- **Collection evidence**: A section on the dashboard headed `Collection evidence` in English and `採集紀錄` in Traditional Chinese. It lists the twelve most recent collection-path logs. Each entry shows success, fallback, or fail. Evidence is not only an off-page log file.
- **Language persistence**: Persist the language choice in localStorage under `hk-index-lang`.


## Dashboard UI Requirements (must implement)
1. **Full index names**: Display full names instead of abbreviations:
   - Centa-City Leading Index (instead of CCL)
   - Rating and Valuation Department Private Domestic Price Index (instead of RVD)
   - Midland Realty Property Price Index (instead of Midland)
2. **Download buttons**: Provide a clear button or link for each series that lets the user download the full dataset currently stored in the local SQL database (CSV or Excel format). The Midland download is the full weekly history in SQL, not only the latest point.
3. **Language switch**: The UI must support switching between English and Traditional Chinese. All labels, headings, insight text, chart titles, and button text should be available in both languages. Store translations or use a simple language toggle. Persist the selected language in localStorage under `hk-index-lang`, using `en` or `zh-Hant`. If the key is missing, use Traditional Chinese when the browser language starts with `zh`, and English otherwise. Any other stored value is treated as English.
4. **Weekly AI update notice**: Show this sentence where it is visible as soon as the dashboard opens, above the charts and tables. It must change with the language switch and use these exact strings:
   - English: `Data is fetched, processed, and updated by AI automatically every week.`
   - Traditional Chinese: `數據由 AI 每週自動擷取、處理並更新。`
5. **History charts**: Show one history chart per index, not only the Centa-City Leading Index, and not one combined chart. The Centa-City Leading Index chart is the long weekly series, with dates as YYYY-MM-DD. The Rating and Valuation Department Private Domestic Price Index chart is monthly, with labels as YYYY-MM. The Midland Realty Property Price Index chart is weekly, and a short series still draws a point for each reading. An empty series shows an empty state and leaves the other charts in place. Chart titles and labels follow the language switcher. The three series use different base periods, so they stay on separate charts.
6. **Author**: Show the name Dominic Yu and the email dominic@data-science-hk.org on the dashboard.
7. **Page title and eyebrow**: The document title and the page heading are `Hong Kong property indices · Dominic Yu` in English and `香港樓價指數 · Dominic Yu` in Traditional Chinese. The eyebrow above the title is `One site with patterns, many sites with Firecrawl` in English and `單一網站靠規律，多個網站靠 Firecrawl` in Traditional Chinese. Both switch with the language control.
8. **Latest-reading cards**: Show one card per index under the heading `Latest readings` / `最新讀數`. Each card shows the full name, the latest value, the as-of date (`As of` / `截至`), the base period, the percent change versus the previous reading (`up` / `down`, `上升` / `下跌`), a provisional badge (`provisional` / `暫定`) when the reading is provisional, how many readings are stored (`readings stored` / `筆已入庫`), a source/path label, and the download button (`Download dataset` / `下載數據`). Leave the change blank when there is no previous reading. Up is a positive change and down is a negative change. The base periods are: Centa-City Leading Index, `July 1997 = 100` / `1997年7月 = 100`; Rating and Valuation Department Private Domestic Price Index, `1999 = 100` / `1999年 = 100`; Midland Realty Property Price Index, `Published index points` / `公布指數點`. The source/path label names the path that stored the latest reading, and the card also links to the official page (`Source` / `來源`). The path labels are `History API` / `歷史接口`, `Weekly page update` / `每週頁面更新`, `Tavily + Firecrawl`, `Playwright fallback` / `Playwright 後備`, `Official file` / `官方檔案`, and `Official page` / `官方頁面`.
9. **Collection evidence**: The dashboard includes a section headed `Collection evidence` in English and `採集紀錄` in Traditional Chinese. It lists the twelve most recent collection-path logs. Each entry shows success, fallback, or fail, as `Succeeded` / `成功`, `Fallback` / `改用後備`, or `Failed` / `失敗`, together with when the step ran, the step name, and the detail when one was logged. With no logs yet, the section says `No collection runs yet.` / `尚未有採集紀錄。` Evidence is not only an off-page log file.

## Consistency Rules
- Always create `.env.example` as specified.
- Fixed file names and structure.
- Do not invent extra tool orders.
- README must cover both Windows and Linux.
- Ollama Cloud insight generation is required, not optional.
- Do not use computer-use models, VLMs, or screenshot-based extraction.
- Always display full index names in the UI.
- Midland is one series only: the territory-wide weekly All / 全港 index. Do not store a second Midland level beside it.

## Presentation Story
**Title: “One Site with Patterns, Many Sites with Firecrawl”**

A Hong Kong property analyst needs the Centa-City Leading Index every week. Pattern-based Playwright works reliably for Centanet because the structure is known.  
But when the analyst also wants the official Rating and Valuation Department index and the Midland Property Price Index, writing new selectors for each site is fragile.  
By routing the Rating and Valuation Department and Midland through Tavily + Firecrawl, the same pipeline extracts their latest values without hard-coded patterns. Midland stays the one territory-wide weekly series from the official market-insight page. A reading from another figure on that page is refused, and a confirmed official run replaces the stored Midland history so two levels cannot share the line.  
After the numbers are stored, Ollama Cloud automatically writes a short comparison insight.  
The dashboard shows a separate history chart for each index, because the three series do not share a base period. The Centa-City Leading Index chart is weekly, with dates as YYYY-MM-DD. The Rating and Valuation Department chart is monthly, labelled YYYY-MM. Every Midland reading gets a point, even when the series is short. An empty series shows an empty state and leaves the other charts in place. Chart titles follow the language switch.  
The page uses full index names, lets users download each complete dataset, including the Midland history already in SQL, supports both English and Traditional Chinese, names Dominic Yu (dominic@data-science-hk.org), and states that the data is fetched, processed, and updated by AI automatically every week.  
The page title is `Hong Kong property indices · Dominic Yu` / `香港樓價指數 · Dominic Yu`, with the eyebrow `One site with patterns, many sites with Firecrawl` / `單一網站靠規律，多個網站靠 Firecrawl` above it. Each latest-reading card shows the full name, the latest value, the as-of date, the base period, the percent change versus the previous reading (up or down), a provisional badge when the reading is provisional, how many readings are stored, a source/path label, and the download button. A Collection evidence / 採集紀錄 section on the page lists the twelve most recent collection-path logs with success, fallback, or fail status. The language choice is stored in localStorage under `hk-index-lang`.  
The result is a single bilingual dashboard with a history chart for each index, live comparison, downloadable data, and a readable insight.

## Must Demonstrate
- Centa-City Leading Index full history in SQL + weekly Playwright update
- Tavily + Firecrawl successfully extracting latest Rating and Valuation Department and Midland Property Price Index values
- Midland kept as the one territory-wide weekly series (the All / 全港 index on the market-insight page, `mrIndexWeekly[].mr_index`). An incompatible reading — a different series name or scope, or a large level gap such as the old mix of readings around 148–149 and a cluster around 110 — is refused, not upserted. A confirmed official run replaces the Midland rows with the published weekly history. The Midland download is that full history.
- Required Ollama Cloud insight generated and displayed
- Live dashboard showing all three indices with **full names**
- A separate history chart for each index: Centa-City Leading Index weekly with dates as YYYY-MM-DD, Rating and Valuation Department Private Domestic Price Index monthly with labels as YYYY-MM, and Midland Realty Property Price Index weekly with a point per reading. An empty series shows an empty state and leaves the other charts in place. Chart titles and labels follow the language switcher. The charts are not combined onto one scale.
- Download buttons for each full dataset
- The dashboard shows Dominic Yu and dominic@data-science-hk.org
- UI language switch between English and Traditional Chinese
- Language choice persisted in localStorage under `hk-index-lang`
- Visible weekly AI update notice in both English and Traditional Chinese, using the exact sentences in the dashboard UI requirements
- Page title `Hong Kong property indices · Dominic Yu` / `香港樓價指數 · Dominic Yu`, and eyebrow `One site with patterns, many sites with Firecrawl` / `單一網站靠規律，多個網站靠 Firecrawl`
- Latest-reading cards that show, for each index, the full name, latest value, as-of date, base period, percent change versus the previous reading (up or down), a provisional badge when the reading is provisional, how many readings are stored, a source/path label, and the download button
- A Collection evidence / 採集紀錄 section on the dashboard that lists the twelve most recent collection-path logs with success, fallback, or fail status. Evidence is not only an off-page log file.
- Evidence records for each path


## Tavily Fallback Behavior
Tavily is optional. If `TAVILY_API_KEY` is missing or Tavily fails, the pipeline must fall back to the known official seed URLs for the Rating and Valuation Department and Midland Property Price Index pages, then continue with Firecrawl. This ensures the run can still complete successfully. Document this behavior in the path log.  
For Midland, still check `https://www.midland.com.hk/en/market-insight/` first, even when Tavily returns another Midland URL. The series taken from that page is the territory-wide weekly All / 全港 index, not a second chart from the same site.
