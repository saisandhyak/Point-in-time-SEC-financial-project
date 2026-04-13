import os
import sqlite3
import json
import sys
import time
import urllib.request
import urllib.error


SEC_USER_AGENT = "YourName yourname@email.com"
DB_PATH        = "pit_sec_data.db"
CIK            = "" #enter the CIK of the company you want to. 
METRIC         = ""
PERIOD_END     = "" # select the date that you want to see the values for. the values will only be shown if they are available on that particular day.
AS_OF_DATE     = ""
SEARCH_TAGS    = ""

try:
    from tabulate import tabulate
    HAS_TABULATE = True
except ImportError:
    HAS_TABULATE = False


def create_database(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS observations (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            cik               TEXT NOT NULL,
            tag               TEXT NOT NULL,
            taxonomy          TEXT NOT NULL,
            units             TEXT NOT NULL,
            period_start      TEXT,
            period_end        TEXT NOT NULL,
            value             REAL NOT NULL,
            accession_number  TEXT NOT NULL,
            filed_date        TEXT NOT NULL,
            form_type         TEXT NOT NULL,
            fiscal_year       INTEGER,
            fiscal_period     TEXT,
            UNIQUE (cik, tag, accession_number, period_end)
        )
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_pit_lookup
        ON observations (cik, tag, period_end, filed_date)
    """)

    conn.commit()
    conn.close()


def fetch_from_sec(cik, metric, user_agent):
    cik_padded = cik.zfill(10)

    if metric.upper() == "ALL":
        url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik_padded}.json"
        print(f"Fetching ALL facts for CIK {cik_padded}...")
    else:
        url = f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik_padded}/us-gaap/{metric}.json"
        print(f"Fetching {metric} for CIK {cik_padded}...")

    req = urllib.request.Request(url, headers={"User-Agent": user_agent})

    try:
        time.sleep(0.11)
        with urllib.request.urlopen(req) as response:
            raw = json.loads(response.read().decode("utf-8"))
        return raw
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"ERROR 404: Not found — CIK '{cik_padded}' or metric '{metric}' does not exist.")
        elif e.code == 403:
            print(f"ERROR 403: Forbidden — check your SEC_USER_AGENT header: '{user_agent}'")
        else:
            print(f"ERROR {e.code}: SEC API returned an error — {e.reason}")
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"ERROR: Could not reach SEC API — {e.reason}")
        sys.exit(1)


def clean_facts(raw_json, cik, metric):
    cik_padded = cik.zfill(10)
    cleaned = []

    def _s(raw):
        return raw.strip() if isinstance(raw, str) and raw.strip() else None

    def process_tag_unit(tag_name, taxonomy, unit_label, observations):
        for obs in observations:
            val = obs.get("val")
            if val is None:
                continue
            try:
                value = float(val)
            except (TypeError, ValueError):
                continue

            period_end = _s(obs.get("end"))
            if not period_end:
                continue

            accession  = _s(obs.get("accn"))
            filed_date = _s(obs.get("filed"))
            form_type  = _s(obs.get("form"))

            if not accession or not filed_date or not form_type:
                continue

            cleaned.append({
                "cik":              cik_padded,
                "tag":              tag_name.strip(),
                "taxonomy":         taxonomy.strip(),
                "units":            unit_label.strip(),
                "period_start":     _s(obs.get("start")),
                "period_end":       period_end,
                "value":            value,
                "accession_number": accession,
                "filed_date":       filed_date,
                "form_type":        form_type,
                "fiscal_year":      obs.get("fy"),
                "fiscal_period":    _s(obs.get("fp")),
            })

    if metric.upper() == "ALL":
        facts_block = raw_json.get("facts", {})
        for taxonomy, tags in facts_block.items():
            for tag_name, tag_data in tags.items():
                units_block = tag_data.get("units", {})
                for unit_label, observations in units_block.items():
                    process_tag_unit(tag_name, taxonomy, unit_label, observations)
    else:
        taxonomy = raw_json.get("taxonomy", "us-gaap")
        tag_name = raw_json.get("tag", metric)
        units_block = raw_json.get("units", {})
        for unit_label, observations in units_block.items():
            process_tag_unit(tag_name, taxonomy, unit_label, observations)

    print(f"Cleaned {len(cleaned)} observations.")
    return cleaned


def store_observations(db_path, clean_facts_list):
    if not clean_facts_list:
        print("Nothing to store.")
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM observations")
    count_before = cur.fetchone()[0]

    cur.executemany("""
        INSERT OR IGNORE INTO observations (
            cik, tag, taxonomy, units,
            period_start, period_end, value,
            accession_number, filed_date, form_type,
            fiscal_year, fiscal_period
        ) VALUES (
            :cik, :tag, :taxonomy, :units,
            :period_start, :period_end, :value,
            :accession_number, :filed_date, :form_type,
            :fiscal_year, :fiscal_period
        )
    """, clean_facts_list)

    conn.commit()

    cur.execute("SELECT COUNT(*) FROM observations")
    count_after = cur.fetchone()[0]
    conn.close()

    inserted = count_after - count_before
    skipped = len(clean_facts_list) - inserted
    print(f"Inserted {inserted} new rows ({skipped} skipped — already in database).")


def query_history(db_path, cik, metric, period_end, as_of_date):
    cik_padded = cik.zfill(10)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    if not as_of_date:
        cur.execute("""
            SELECT filed_date, value, form_type, accession_number,
                   fiscal_year, fiscal_period
            FROM observations
            WHERE cik = ? AND tag = ? AND period_end = ?
            ORDER BY filed_date ASC
        """, (cik_padded, metric, period_end))
    else:
        cur.execute("""
            SELECT filed_date, value, form_type, accession_number,
                   fiscal_year, fiscal_period
            FROM observations
            WHERE cik = ? AND tag = ? AND period_end = ? AND filed_date <= ?
            ORDER BY filed_date DESC
            LIMIT 1
        """, (cik_padded, metric, period_end, as_of_date))

    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    if not rows:
        print(f"\nNo observations found for CIK {cik_padded} | {metric} | period ending {period_end}"
              + (f" | as-of {as_of_date}" if as_of_date else "") + ".")

    return rows


def print_available_periods(db_path, cik, metric):
    cik_padded = cik.zfill(10)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        SELECT period_end, COUNT(*) as obs_count
        FROM observations
        WHERE cik = ? AND tag = ?
        GROUP BY period_end
        ORDER BY period_end
    """, (cik_padded, metric))
    rows = cur.fetchall()
    conn.close()

    print(f"\nAvailable periods for {metric}:")
    if not rows:
        print("  (none — no data stored for this CIK + tag)")
    else:
        for period_end, obs_count in rows:
            print(f"  {period_end}  ({obs_count} observation{'s' if obs_count != 1 else ''})")


def search_tags(db_path, cik, keyword):
    cik_padded = cik.zfill(10)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        SELECT tag,
               MIN(period_end) AS earliest,
               MAX(period_end) AS latest,
               COUNT(*)        AS obs_count
        FROM observations
        WHERE cik = ? AND tag LIKE '%' || ? || '%'
        GROUP BY tag
        ORDER BY tag
    """, (cik_padded, keyword))
    rows = cur.fetchall()
    conn.close()

    print(f"\nTags matching \"{keyword}\" for CIK {cik_padded}:")
    if not rows:
        print("  (no matching tags found — try a broader keyword or run METRIC=\"ALL\" first)")
    else:
        for tag, earliest, latest, obs_count in rows:
            print(f"  {tag:<60}  {earliest} → {latest}  ({obs_count} obs)")


def print_table(results, query_mode_label, cik, metric, period_end, as_of_date):
    cik_padded = cik.zfill(10)

    if as_of_date:
        header = f"As-Of {as_of_date}: CIK {cik_padded} | {metric} | Period ending {period_end}"
    else:
        header = f"Full History: CIK {cik_padded} | {metric} | Period ending {period_end}"

    print(f"\n{header}")

    if not results:
        print("No observations found for these parameters.")
        return

    columns = ["filed_date", "value", "form_type", "accession_number", "fiscal_year", "fiscal_period"]
    rows = [[r[c] for c in columns] for r in results]

    if HAS_TABULATE:
        print(tabulate(rows, headers=columns, tablefmt="simple"))
    else:
        col_widths = [max(len(str(col)), max((len(str(r[i])) for r in rows), default=0))
                      for i, col in enumerate(columns)]
        sep = "-+-".join("-" * w for w in col_widths)
        header_row = " | ".join(str(col).ljust(col_widths[i]) for i, col in enumerate(columns))
        print(header_row)
        print(sep)
        for row in rows:
            print(" | ".join(str(cell).ljust(col_widths[i]) for i, cell in enumerate(row)))

    print()


if __name__ == "__main__":

    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    create_database(DB_PATH)

    raw   = fetch_from_sec(CIK, METRIC, SEC_USER_AGENT)
    clean = clean_facts(raw, CIK, METRIC)
    store_observations(DB_PATH, clean)

    if SEARCH_TAGS:
        search_tags(DB_PATH, CIK, SEARCH_TAGS)
        sys.exit(0)

    print_available_periods(DB_PATH, CIK, METRIC)

    if not PERIOD_END:
        print('\nSet PERIOD_END to one of the dates above and run again.')
        sys.exit(0)

    results    = query_history(DB_PATH, CIK, METRIC, PERIOD_END, AS_OF_DATE)
    mode_label = "as_of" if AS_OF_DATE else "full_history"
    print_table(results, mode_label, CIK, METRIC, PERIOD_END, AS_OF_DATE)
