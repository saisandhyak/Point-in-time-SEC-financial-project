# Point-in-Time SEC Financial Data

Most financial data platforms show you one number for any metric, the latest one. But that number may have been revised in a later filing. The old value gets overwritten, and there's no way to know it ever changed.

This project fixes that. It pulls **every version** of every financial fact a public US company has reported to the SEC, stores them all with the exact date each version became public, and lets you query: "What was this number as of March 1st, 2024?" without accidentally using information that didn't exist yet.

One Python script. One SQLite database. Works for any public US company. No paid APIs.

---

## Where This Idea Came From

This project came from work I'm currently doing at Omnesys, where I noticed that most platforms only show the latest reported value, not what was actually known on a particular date.

Think about it: if a researcher or analyst wants to know what a number looked like on a specific date, they can't just find that on the SEC website. It doesn't exist there. The SEC shows you the filing, but not the timeline of how a value changed across multiple filings.

With the pipeline I built, researchers can get that information accurately. All the historical data is stored in a SQLite database in a structured way — you can see the full history of any value, including which filing reported it and on what date the company posted it.

And this isn't limited to one company. It works for thousands of companies, you just change the ticker and specify which date and metric you're interested in. 

---

## A Real Example

This isn't theoretical. During development, the platform caught an actual silent revision:

| Filed Date | Value | Form | Accession Number |
|---|---|---|---|
| 2023-11-03 | $8,200,000,000 | 10-K | 0000320193-23-000106 |
| 2024-11-01 | $8,200,000,000 | 10-K | 0000320193-24-000123 |
| 2025-10-31 | **$8,169,000,000** | 10-K | 0000320193-25-000079 |

Same company, same metric, same business period — but the third filing quietly changed the value by $31 million. Most platforms would only show you that last number. This tool shows the full timeline.

I verified the original value against the actual SEC filing on sec.gov. The numbers matched.

---

## How It Works

The script calls the **SEC EDGAR XBRL API** directly, it's free, no API key required. The SEC already parses every filing into structured XBRL data and makes it available through a public API at `data.sec.gov`. This pipeline downloads that data, cleans it, and stores it locally.

Every stored number carries two timestamps:

- **period_end**- the fiscal period the number describes
- **filed_date**- the date the SEC filing that reported this number became public

Keeping these two dates separate is what makes point-in-time queries possible. You always know what a number was *about* and when it was *known*.

### The Pipeline

```
Step 1: Create database     - opens or creates the .db file
Step 2: Fetch from SEC      - calls the XBRL API, downloads raw JSON
Step 3: Clean observations  - normalizes dates, types, handles nulls
Step 4: Store in SQLite     - INSERT OR IGNORE (safe to re-run)
Step 5: Show available data - prints periods or tag search results
Step 6: Query and display   - runs the requested query, prints results
```

### Three Operating Modes

**Ingest mode** - Set `METRIC = "ALL"` to download every fact for a company. One API call, thousands of observations, stored permanently.

**Search mode** - Set `SEARCH_TAGS = "Revenue"` (or any keyword) to find the exact XBRL tag names a company uses. Shows matching tags with their date ranges.

**Query mode** - Set a specific metric and period to see the full revision history. Optionally set an as-of date for a point-in-time answer.

---

## Getting Started

### 1. Clone and Install

```bash
git clone https://github.com/yourusername/pit-sec-data.git
cd pit-sec-data
pip install tabulate   # optional, for prettier table output
```

### 2. Set Your Identity

Open `pit_sec_data.py` and change the first line:

```python
SEC_USER_AGENT = "YourName yourname@email.com"   # CHANGE THIS — required by SEC
```

The SEC requires a user-agent string with your name and email for API access. No registration or API key needed.

### 3. Run It

```bash
python pit_sec_data.py
```

On the first run with default settings, it downloads all facts for the default company and shows available period dates. The database file is created automatically next to the script.

### 4. Explore

Change the config variables at the top of the file to try different companies, metrics, and dates:

```python
CIK            = "0000789019"    # Microsoft
METRIC         = "ALL"           # Download everything
SEARCH_TAGS    = "Revenue"       # Find revenue-related tags
```

---

## Configuration Reference

All configuration lives in the first few lines of the file. Edit these before running.

| Variable | What It Does | Example |
|---|---|---|
| `SEC_USER_AGENT` | Your name and email (required by SEC) | `"Jane Doe jane@email.com"` |
| `DB_PATH` | SQLite database file path | `"pit_sec_data.db"` |
| `CIK` | 10-digit company identifier | `"0000320193"` |
| `METRIC` | XBRL tag name, or `"ALL"` | `"Revenues"` or `"ALL"` |
| `PERIOD_END` | Fiscal period end date, or `""` for discovery | `"2023-09-30"` or `""` |
| `AS_OF_DATE` | Point-in-time date, or `""` for full history | `"2024-02-01"` or `""` |
| `SEARCH_TAGS` | Keyword to search tag names, or `""` | `"Revenue"` or `""` |

---

## Common Company CIKs

| Company | Ticker | CIK |
|---|---|---|
| Apple | AAPL | 0000320193 |
| Microsoft | MSFT | 0000789019 |
| Alphabet / Google | GOOG | 0001652044 |
| Amazon | AMZN | 0001018724 |
| Tesla | TSLA | 0001318605 |
| Meta | META | 0001326801 |
| NVIDIA | NVDA | 0001045810 |
| Netflix | NFLX | 0001065280 |
| JPMorgan Chase | JPM | 0000019617 |
| Berkshire Hathaway | BRK | 0001067983 |

Find any company's CIK at: https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany

---

## Typical Workflow

### First Time With a New Company

```
Run 1:  METRIC = "ALL"                              → downloads everything
Run 2:  SEARCH_TAGS = "Revenue"                     → find the right tag name
Run 3:  METRIC = "RevenueFromContract...", PERIOD_END = ""  → see available dates
Run 4:  PERIOD_END = "2023-06-30"                   → see full revision history
```

### Point-in-Time Query

```python
METRIC     = "RevenueFromContractWithCustomerExcludingAssessedTax"
PERIOD_END = "2023-09-30"
AS_OF_DATE = "2024-02-01"    # what was known on Feb 1, 2024?
```

Returns exactly one row — the most recent value that existed on or before that date. Anything filed after that date is excluded.

### Finding Tag Names

Companies use different XBRL tag names for the same concept, and they sometimes change tags over time. Here are some useful search keywords:

| You Want | Search With |
|---|---|
| Revenue | `SEARCH_TAGS = "Revenue"` |
| Net income | `SEARCH_TAGS = "NetIncome"` |
| Total assets | `SEARCH_TAGS = "Assets"` |
| Cash | `SEARCH_TAGS = "Cash"` |
| Debt | `SEARCH_TAGS = "Debt"` |
| Equity | `SEARCH_TAGS = "Equity"` |
| Receivables | `SEARCH_TAGS = "Receivable"` |
| OCI | `SEARCH_TAGS = "Comprehensive"` |

---

## Database Schema

One table stores everything:

```
observations
├── id                 INTEGER    auto-increment primary key
├── cik                TEXT       10-digit company ID
├── tag                TEXT       XBRL metric name
├── taxonomy           TEXT       reporting standard (us-gaap, dei)
├── units              TEXT       USD, shares, pure
├── period_start       TEXT       business period start (null for instant facts)
├── period_end         TEXT       business period end
├── value              REAL       the reported number
├── accession_number   TEXT       unique filing ID (links to sec.gov)
├── filed_date         TEXT       when the filing was submitted
├── form_type          TEXT       10-K, 10-Q, 10-K/A, 8-K
├── fiscal_year        INTEGER    fiscal year of the filing
└── fiscal_period      TEXT       FY, Q1, Q2, Q3
```

**Index:** `(cik, tag, period_end, filed_date)` — keeps all query patterns fast.

**Uniqueness:** `(cik, tag, accession_number, period_end)` — prevents duplicate rows on re-runs.

The database is append-only. No rows are ever updated or deleted. Every run adds new data alongside what's already there. Multiple companies can coexist in the same database.

---

## How to Validate the Data

Every row includes an `accession_number` that links directly to the SEC filing:

1. Take the accession number from your query result (e.g., `0000320193-23-000106`)
2. Remove the dashes and build the URL: `https://www.sec.gov/Archives/edgar/data/[CIK]/[accession-no-dashes]/[accession]-index.htm`
3. Open the filing document
4. Use the XBRL viewer's Search Facts box to find the tagged value

The data comes from the SEC's own parsed XBRL API — the same data they validate and publish. Manual validation is a good sanity check, but the source is already authoritative.

---

## Design Decisions

**Why keep all observations?** - Most SEC data tools deduplicate and only keep the latest value per period. That destroys the revision history. This tool keeps every observation from every filing. If the same value appears in three filings, it stores three rows, each with a different accession number and filed date. That's the audit trail.

**Why SQLite?** - It runs locally, needs no setup, handles millions of rows, and the `.db` file is easy to share. You can also open it in [DB Browser for SQLite](https://sqlitebrowser.org/) to browse the data visually.

**Why the CompanyFacts API and not the Frames API?** - The SEC's Frames API deduplicates by design — it returns only one value per company per period. That's the opposite of what this project needs.

---

## Good to Know

**Fiscal dates can be irregular.** A fiscal year ending "September 2023" might actually be 2023-09-30, 2023-09-24, or 2023-10-01 depending on the company. Always use discovery mode (`PERIOD_END = ""`) to check the exact dates first.

**Tag names change over time.** A company might use one XBRL tag for years, then switch to a different one for the same concept. Use `SEARCH_TAGS` to find the current tag and check date ranges.

**Duration facts vs instant facts.** Revenue has both a `period_start` and `period_end` (it's measured over a time range). Total assets only has a `period_end` with `period_start` as null (it's a snapshot at one point in time).

**Re-runs are safe.** The script uses `INSERT OR IGNORE`, so running it multiple times won't create duplicate data.

**Multiple companies, one database.** Every run adds data alongside what's already stored. Just filter by CIK when querying.

---

## Data Source

All data comes from the SEC EDGAR XBRL API:

- **CompanyFacts:** `https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json`
- **CompanyConcept:** `https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/{tag}.json`
- **API Docs:** https://www.sec.gov/search-filings/edgar-application-programming-interfaces

No API key required. Free to use. Rate limit: 10 requests per second.
