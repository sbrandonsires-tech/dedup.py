-- schema.sql — TRS Deal Sourcing Pipeline
-- Every target from every source flows into one unified `companies` table.

CREATE TABLE IF NOT EXISTS companies (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name        TEXT NOT NULL,
    source              TEXT NOT NULL,           -- 'edgar', 'sam', 'osha', 'bizbuysell', etc.
    source_id           TEXT,                    -- External ID from source system
    date_added          TEXT NOT NULL,           -- ISO 8601: 2026-01-15
    last_updated        TEXT,
    -- Location
    state               TEXT,
    city                TEXT,
    zip                 TEXT,
    address             TEXT,
    -- Classification
    sic_code            TEXT,
    naics_code          TEXT,
    trs_sector          TEXT,                    -- 'Manufacturing', 'Distribution', 'Services'
    trs_subsector       TEXT,                    -- e.g., 'Electrical Distribution', 'Fabricated Metal'
    -- Size proxies (not actuals — labelled as estimates)
    revenue_estimate_low    REAL,
    revenue_estimate_high   REAL,
    ebitda_estimate         REAL,
    employee_count_low      INTEGER,
    employee_count_high     INTEGER,
    employee_band           TEXT,                -- e.g., '10-49', '50-99'
    -- Ownership signals
    owner_name          TEXT,
    owner_age_proxy     TEXT,                    -- 'likely 50+', 'unknown'
    years_in_business   INTEGER,
    founded_year        INTEGER,
    filing_status       TEXT,                    -- 'active', 'lapsed', 'dormant'
    -- Exit pressure signals
    osha_violation_count    INTEGER DEFAULT 0,
    osha_last_inspection    TEXT,
    osha_severity           TEXT,                -- 'none', 'low', 'medium', 'high'
    ucc_filing_count        INTEGER DEFAULT 0,
    ucc_latest_maturity     TEXT,
    sba_loan_flag           INTEGER DEFAULT 0,   -- 1 if SBA loan / small-business flag detected
    -- Broker listing fields (BizBuySell / DealStream / AM&AA)
    asking_price        REAL,
    listed_revenue      REAL,
    listed_cash_flow    REAL,
    days_on_market      INTEGER,
    broker_name         TEXT,
    broker_email        TEXT,
    listing_url         TEXT,
    -- Scoring
    score_total         INTEGER DEFAULT 0,       -- 0-100
    score_sector        INTEGER DEFAULT 0,
    score_geography     INTEGER DEFAULT 0,
    score_size          INTEGER DEFAULT 0,
    score_ownership     INTEGER DEFAULT 0,
    score_stress        INTEGER DEFAULT 0,
    tier                INTEGER DEFAULT 3,        -- 1, 2, or 3
    -- Pipeline status (user-managed; never overwritten by reruns once set)
    pipeline_stage      TEXT DEFAULT 'Identified',
    -- Stages: Identified, Screened, Diligence, LOI, Closed, Passed
    assigned_to         TEXT DEFAULT 'Brandon',
    next_action         TEXT,
    next_action_date    TEXT,
    notes               TEXT,
    -- Excel sync
    excel_exported      INTEGER DEFAULT 0,       -- 1 = included in last Excel export
    -- Raw data
    raw_data            TEXT                     -- JSON blob of original API response
);

CREATE TABLE IF NOT EXISTS run_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date        TEXT NOT NULL,
    source          TEXT NOT NULL,
    records_pulled  INTEGER DEFAULT 0,
    records_new     INTEGER DEFAULT 0,
    records_updated INTEGER DEFAULT 0,
    tier1_count     INTEGER DEFAULT 0,
    tier2_count     INTEGER DEFAULT 0,
    errors          TEXT,
    duration_seconds REAL
);

CREATE INDEX IF NOT EXISTS idx_tier ON companies(tier);
CREATE INDEX IF NOT EXISTS idx_state ON companies(state);
CREATE INDEX IF NOT EXISTS idx_source ON companies(source);
CREATE INDEX IF NOT EXISTS idx_pipeline_stage ON companies(pipeline_stage);
CREATE INDEX IF NOT EXISTS idx_excel_exported ON companies(excel_exported);
-- Dedup lookups hit company_name + state constantly.
CREATE INDEX IF NOT EXISTS idx_name_state ON companies(company_name, state);
