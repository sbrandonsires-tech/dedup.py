"""Census County Business Patterns (CBP) - universe map by NAICS and county.

KEYLESS PATH: the live CBP data API now requires an API key (it redirects to
missing_key.html). To stay keyless we use the CBP *bulk flat file* instead, which
is fully public:
    https://www2.census.gov/programs-surveys/cbp/datasets/<year>/cbp<yy>co.zip

CBP gives establishment counts and employment-size-class distributions by county
and NAICS. It does not name individual companies, so this module builds the
universe denominator (how many establishments exist, and how big) rather than
company records. Narrow 5-digit NAICS cells are frequently disclosure-suppressed
(shown as "N"); we surface that honestly in the output.
"""

from __future__ import annotations

import io
import zipfile

import pandas as pd

from .. import http, settings

CBP_YEAR = 2022
CBP_URL = f"https://www2.census.gov/programs-surveys/cbp/datasets/{CBP_YEAR}/cbp{str(CBP_YEAR)[2:]}co.zip"

# Two-letter state -> FIPS state code, for the priority/secondary geographies.
STATE_FIPS = {
    "IL": "17", "IN": "18", "OH": "39", "MI": "26", "WI": "55", "MN": "27",
    "PA": "42", "NY": "36", "NJ": "34", "MA": "25", "CT": "09", "IA": "19",
    "MO": "29", "KY": "21", "MD": "24",
}
FIPS_STATE = {v: k for k, v in STATE_FIPS.items()}

SIZE_BANDS = ["n<5", "n5_9", "n10_19", "n20_49", "n50_99",
              "n100_249", "n250_499", "n500_999", "n1000"]


def _norm_naics(code: str) -> str:
    """Strip CBP padding ('/' and '-') so '33592/' -> '33592'."""
    return str(code).replace("/", "").replace("-", "").strip()


def _load_frame() -> pd.DataFrame | None:
    raw = http.get(CBP_URL, binary=True, check_robots=False)
    if raw is None:
        return None
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        member = next(n for n in zf.namelist() if n.lower().endswith(".txt"))
        with zf.open(member) as fh:
            usecols = ["fipstate", "fipscty", "naics", "emp", "est", *SIZE_BANDS]
            df = pd.read_csv(fh, usecols=usecols, dtype=str)
    return df


def build_universe_map(states: list[str], naics_codes: list[str]) -> pd.DataFrame:
    """Return CBP rows for the requested states x NAICS codes, tidied."""
    df = _load_frame()
    if df is None:
        return pd.DataFrame()

    want_fips = {STATE_FIPS[s] for s in states if s in STATE_FIPS}
    want_naics = {_norm_naics(c) for c in naics_codes}

    df["naics_norm"] = df["naics"].map(_norm_naics)
    mask = df["fipstate"].isin(want_fips) & df["naics_norm"].isin(want_naics)
    out = df.loc[mask].copy()

    out["state"] = out["fipstate"].map(FIPS_STATE)
    out["county_fips"] = out["fipstate"] + out["fipscty"]
    out["emp"] = pd.to_numeric(out["emp"], errors="coerce").fillna(0).astype(int)
    out["est"] = pd.to_numeric(out["est"], errors="coerce").fillna(0).astype(int)
    cols = ["state", "county_fips", "naics_norm", "naics", "est", "emp", *SIZE_BANDS]
    return out[cols].sort_values(["state", "naics_norm", "county_fips"]).reset_index(drop=True)


def run(conn, *, states: list[str], naics_codes: list[str]) -> dict:
    """Build and persist the universe map. Logged to run_log; consumed by Excel."""
    print(f"[census] CBP {CBP_YEAR} universe map: states={states} naics={naics_codes}")
    df = build_universe_map(states, naics_codes)

    out_path = settings.DATA_DIR / "universe_map.csv"
    df.to_csv(out_path, index=False)

    total_est = int(df["est"].sum()) if not df.empty else 0
    total_emp = int(df["emp"].sum()) if not df.empty else 0
    n_counties = df["county_fips"].nunique() if not df.empty else 0
    suppressed = 0
    if not df.empty:
        suppressed = int((df[SIZE_BANDS] == "N").all(axis=1).sum())

    notes = (f"CBP {CBP_YEAR} bulk county file. "
             f"{total_est} establishments, {total_emp} employees across "
             f"{n_counties} counties; {suppressed} county-NAICS cells fully "
             f"size-suppressed.")
    fetch_date = http.fetched_at(CBP_URL) or ""
    db_log_source = "census"

    from .. import db
    db.log_run(conn, db_log_source, pulled=len(df), notes=notes)

    print(f"  {notes}")
    print(f"  universe map written to {out_path}")
    return {
        "rows": len(df),
        "total_establishments": total_est,
        "total_employees": total_emp,
        "counties": n_counties,
        "suppressed_cells": suppressed,
        "csv_path": str(out_path),
        "fetch_date": fetch_date,
        "source_url": CBP_URL,
        "dataframe": df,
    }
