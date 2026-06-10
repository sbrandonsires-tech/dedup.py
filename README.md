# TRS Investments - Deal Sourcing Pipeline

A keyless deal-sourcing pipeline for lower-middle-market industrial acquisitions.
Every data source is publicly accessible **without authentication**: no paid APIs,
no API keys, no `.env`. Scraping is polite (real User-Agent, robots.txt respected,
1 request / 2 seconds, every raw response cached so re-runs never re-fetch).

> Status: **schema + EDGAR + Census + test run** are built. Remaining sources
> (OSHA, EPA ECHO, State Secretary of State registries, company-website crawl) and
> the web-enrichment pass are scaffolded in the architecture and planned next.

## Target profile

North American industrial manufacturing, value-add distribution, and B2B
industrial services. Priority niches: wire harness, cable assembly, electrical /
electronic components distribution, wire and cable, connectors, industrial MRO.
Revenue $4M to $30M, EBITDA $800K to $5M, founder/family owned, succession
signals, Midwest and Northeast weighted highest, Canada acceptable. The full
profile lives in `config/targets.yaml` and drives all scoring.

## Setup

```bash
pip install -r requirements.txt        # requests, beautifulsoup4, pandas, openpyxl, pyyaml
```

No keys to configure. The first run downloads and caches a Census bulk file
(~14 MB) into `cache/`.

## Running

```bash
python pipeline.py run                       # full pass: all sources, score, export
python pipeline.py run --source edgar        # one source, then score + export
python pipeline.py run --states IL,IN --naics 33592,335921,335929
python pipeline.py rescore                   # re-apply YAML weights, NO re-fetch
python pipeline.py export                     # rebuild Excel from current DB only
```

Default scope is the review scope: **NAICS 33592 (wire and cable) in IL and IN.**
Output Excel lands in `outputs/TRS_Deal_Pipeline_<date>.xlsx`.

## How scoring works

A 0-100 total from five weighted components (weights in `config/weights.yaml`,
editable without touching code; run `rescore` after editing):

| Component        | Weight | Driven by |
|------------------|:------:|-----------|
| Niche fit        | 30 | Priority niche keywords + priority/core NAICS |
| Size fit         | 25 | Revenue / EBITDA / headcount vs. target band (revenue estimated from headcount when financials are absent) |
| Succession       | 25 | Operating history 20+ yrs, owner age 60+, family / generational language, retirement signals |
| Geography        | 10 | Midwest + Northeast highest, Canada acceptable |
| Data confidence  | 10 | Corroboration: number of cited signals and distinct sources |

Every score stores its full component breakdown and per-component rationale in
`scores.breakdown_json` for auditability.

## Data model (SQLite, `data/trs.db`)

Five normalized tables: `companies`, `signals`, `scores`, `contacts`, `run_log`.
Dedup key is **normalized name + state + domain**. Every fact about a company is
an atomic row in `signals` that cites its `source_url` and `fetch_date`.

## Sources built so far

1. **SEC EDGAR** full-text search (`efts.sec.gov`, keyless, descriptive
   User-Agent). Two jobs: flag public filers as **excluded / institutionally
   owned**, and mine filings for **competitor names** (low-confidence, unverified
   candidates). On the test scope it correctly excludes Belden, Anixter, Atkore,
   Coleman Cable, General Cable, Asia Pacific Wire & Cable, etc.
2. **Census County Business Patterns** universe map. The live CBP *API* now
   requires a key, so we use the keyless **bulk county flat file**
   (`www2.census.gov/.../cbp22co.zip`) instead. Builds establishment counts and
   size-class distribution by county and NAICS.

### Test run finding (NAICS 33592, IL + IN)

EDGAR and Census are the two keyless sources that do **not** directly enumerate
private companies, and the test run shows exactly that:

- Census universe map for 33592 is thin and heavily **disclosure-suppressed**:
  only DuPage County, IL surfaces (6 establishments, size bands withheld as "N").
  Indiana counties are suppressed entirely at this 5-digit code.
- EDGAR produces a clean **exclusion set** of public players plus low-confidence
  competitor mentions (many large or foreign), none of which qualify as targets.
- The **Scored Targets** tab is therefore empty by design. Private LMM targets
  come from the next phase: **State Secretary of State registries** (names +
  incorporation year) and **company-website crawling** (founding year, family
  language, owner names). EDGAR/Census are the exclusion filter and the universe
  denominator around those.

## Output workbook

Tabs: **Summary** dashboard, **Scored Targets** (sortable, full score-breakdown
columns), **New This Run**, **Watch List** (60-79), **Source Log**. House style:
navy `#1B365D` headers, Georgia bold headings, Calibri body, blue font on
manually editable cells (Pipeline Stage, Owner/Contact, Notes). No em dashes in
any cell text.

## Hard exclusions (never surfaced on target tabs)

PE/VC-backed or public-subsidiary companies; staffing and construction
pass-through businesses (name blocklist); under 10 or over 250 employees. Excluded
rows are kept in the database for auditability, just never surfaced.

## Data Gaps (the upgrade path a keyed version would add)

This build is deliberately keyless. A keyed/paid tier would add:

- **Census Bureau API key** (free): restores live CBP/County queries instead of
  the bulk file, plus access to less-suppressed tabulations. The bulk file we use
  is fully keyless but suppresses narrow cells more aggressively.
- **DOL / OSHA enforcement API key** (free, issuance intermittent): the OSHA
  *bulk CSV* path is keyless and planned; the API key would add fresher
  inspection data. OSHA confirms a real plant exists and gives employee counts.
- **SAM.gov API key** (free): federal registration data (UEI, NAICS, exact
  address, points of contact) for any target that does government work.
- **Apollo / ZoomInfo** (paid): verified owner names, direct emails and phones,
  org charts. Replaces the unverified contact enrichment.
- **Grata / SourceScrub** (paid): purpose-built private-company search with
  firmographics, ownership, and growth signals; would massively improve the
  target-generation step that State SoS + website crawling does here for free.
- **PitchBook / CB Insights** (paid): authoritative PE/VC ownership data to make
  the institutional-ownership exclusion exhaustive rather than EDGAR-only.
- **D&B / business-credit data** (paid): revenue and employee actuals, replacing
  the headcount-based revenue estimate.

## Repository layout

```
pipeline.py            CLI: run / run --source / rescore / export
config/
  weights.yaml         scoring weights + thresholds (edit, then rescore)
  targets.yaml         niches, NAICS, geography tiers, size band, exclusions
trs/
  settings.py          paths + YAML loading; no keys
  http.py              polite cached client (UA, robots.txt, 2s rate limit)
  schema.sql           companies / signals / scores / contacts / run_log
  db.py                SQLite access + dedup upsert
  normalize.py         name/state/domain normalization + dedup key
  scoring.py           5-component weighted scorer with stored breakdown
  process.py           hard filters, size estimates, rescore
  excel.py             openpyxl workbook
  sources/
    edgar.py           SEC EDGAR full-text search
    census.py          CBP bulk-file universe map
cache/                 raw responses (gitignored; re-runs never re-fetch)
data/                  SQLite db + bulk downloads + universe_map.csv (gitignored)
outputs/               generated Excel workbooks (gitignored)
legacy/                earlier key-dependent prototype, kept for reference
```
