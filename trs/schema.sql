-- TRS deal sourcing - normalized schema.
-- Five tables: companies, signals, scores, contacts, run_log.
-- Dedup key is normalized_name + state + domain (see trs/normalize.py).

CREATE TABLE IF NOT EXISTS companies (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    dedup_key           TEXT NOT NULL UNIQUE,    -- normalized_name|state|domain
    name                TEXT NOT NULL,           -- best display name seen
    normalized_name     TEXT NOT NULL,
    domain              TEXT,                     -- bare registrable domain, lowercased
    state               TEXT,
    county              TEXT,
    city                TEXT,
    naics_code          TEXT,
    naics_label         TEXT,
    sic_code            TEXT,
    -- Size estimates (labelled as estimates; never presented as actuals)
    employee_count      INTEGER,
    employee_band       TEXT,
    revenue_estimate    REAL,
    ebitda_estimate     REAL,
    revenue_basis       TEXT,                     -- how revenue was estimated
    -- Ownership / age signals
    founded_year        INTEGER,
    years_in_business   INTEGER,
    owner_age_estimate  INTEGER,
    institutional_owned INTEGER DEFAULT 0,        -- 1 = PE/VC/public subsidiary
    excluded            INTEGER DEFAULT 0,        -- 1 = fails a hard filter
    exclusion_reason    TEXT,
    -- Provenance
    first_source        TEXT NOT NULL,           -- source module that created the row
    first_seen          TEXT NOT NULL,           -- ISO date
    last_seen           TEXT NOT NULL,
    new_this_run        INTEGER DEFAULT 0         -- 1 if created during the current run
);

-- One row per atomic, sourced fact about a company. This is the audit trail:
-- every signal cites where it came from and when it was fetched.
CREATE TABLE IF NOT EXISTS signals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id      INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    signal_type     TEXT NOT NULL,    -- e.g. 'niche_keyword', 'osha_plant', 'family_owned'
    value           TEXT,             -- the observed value / snippet
    source          TEXT NOT NULL,    -- source module name
    source_url      TEXT,             -- citation URL
    fetch_date      TEXT,             -- ISO date the source was fetched
    confidence      REAL DEFAULT 0.5, -- 0-1, how much we trust this signal
    UNIQUE(company_id, signal_type, value, source_url)
);

-- One row per company per scoring run. Stores the component breakdown so any
-- total can be reconstructed and audited.
CREATE TABLE IF NOT EXISTS scores (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id          INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    run_id              INTEGER,
    scored_at           TEXT NOT NULL,
    total               REAL NOT NULL,
    niche_fit           REAL DEFAULT 0,
    size_fit            REAL DEFAULT 0,
    succession          REAL DEFAULT 0,
    geography           REAL DEFAULT 0,
    data_confidence     REAL DEFAULT 0,
    breakdown_json      TEXT,         -- full per-component rationale
    UNIQUE(company_id, run_id)
);

-- Owner / decision-maker contacts, populated by the enrichment pass.
CREATE TABLE IF NOT EXISTS contacts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id      INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    name            TEXT,
    title           TEXT,
    email           TEXT,
    phone           TEXT,
    source          TEXT,
    source_url      TEXT,
    fetch_date      TEXT,
    UNIQUE(company_id, name, title)
);

CREATE TABLE IF NOT EXISTS run_log (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date            TEXT NOT NULL,
    source              TEXT NOT NULL,
    records_pulled      INTEGER DEFAULT 0,
    records_new         INTEGER DEFAULT 0,
    records_updated     INTEGER DEFAULT 0,
    notes               TEXT,
    duration_seconds    REAL
);

CREATE INDEX IF NOT EXISTS idx_companies_state ON companies(state);
CREATE INDEX IF NOT EXISTS idx_companies_naics ON companies(naics_code);
CREATE INDEX IF NOT EXISTS idx_companies_excluded ON companies(excluded);
CREATE INDEX IF NOT EXISTS idx_signals_company ON signals(company_id);
CREATE INDEX IF NOT EXISTS idx_scores_company ON scores(company_id);
CREATE INDEX IF NOT EXISTS idx_contacts_company ON contacts(company_id);
