"""SEC EDGAR - exclusion set and competitor mining (keyless).

Two jobs, per the spec:
  1. EXCLUDE institutionally owned companies: any company that files with the SEC
     is public (or a public subsidiary / fund), so it is out of thesis. We record
     filers as excluded with institutional_owned=1, which both documents the
     exclusion and maps "who is public" in a niche.
  2. Find competitors named in filings: filings routinely name private
     competitors, customers, and suppliers. We mine filing text for company-like
     names that contain a niche keyword (e.g. "... Wire & Cable") and record them
     as unverified candidate targets, each citing the filing it came from.

Endpoint (no key; requires a descriptive User-Agent per SEC fair-access policy):
    https://efts.sec.gov/LATEST/search-index?q=...&forms=...&from=...
"""

from __future__ import annotations

import re

from .. import db, http, settings

FTS_URL = "https://efts.sec.gov/LATEST/search-index"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{fn}"
PAGE_SIZE = 10
MAX_HITS_PER_QUERY = 60          # paginate up to this many FTS hits
MAX_DOCS_TO_MINE = 12           # cap doc fetches to respect rate limits
MAX_MENTIONS_PER_DOC = 8        # one filing must not flood the candidate pool

# Geographic words that, on their own, are not a company. Guards against matches
# like "...located in Indiana. Manufacturing of..." -> "Indiana Manufacturing".
_PLACE_WORDS = {
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana", "maine",
    "maryland", "massachusetts", "michigan", "minnesota", "mississippi",
    "missouri", "montana", "nebraska", "nevada", "new", "hampshire", "jersey",
    "mexico", "york", "north", "south", "carolina", "dakota", "ohio",
    "oklahoma", "oregon", "pennsylvania", "rhode", "island", "tennessee",
    "texas", "utah", "vermont", "virginia", "washington", "west", "wisconsin",
    "wyoming", "canada", "china", "hungary", "netherlands", "the", "united",
    "kingdom", "thai", "thailand", "taiwan", "japan", "korea", "germany",
    "france", "australia", "pacific", "asia", "europe",
}
_SUFFIX_TOKENS = {
    "wire", "cable", "cabling", "harness", "connector", "connectors",
    "components", "electronics", "electric", "electrical", "industries",
    "manufacturing", "mfg", "assemblies", "assembly",
    "inc", "incorporated", "corp", "corporation", "company", "co", "llc", "ltd",
}

# A company-like proper name ending in an industrial/legal token. Conservative on
# purpose: we only keep names that read like real industrial firms.
_COMPANY_RE = re.compile(
    r"\b([A-Z][A-Za-z&.\-]+(?:\s+[A-Z][A-Za-z&.\-]+){0,4}\s+"
    r"(?:Wire|Cable|Cabling|Harness|Connector|Connectors|Components|Electronics|"
    r"Electric|Electrical|Industries|Manufacturing|Mfg|Assemblies|Assembly)"
    r"(?:,?\s+(?:Inc|Incorporated|Corp|Corporation|Company|Co|LLC|Ltd))?\.?)\b"
)


def _parse_id(doc_id: str, cik: str) -> str | None:
    if ":" not in doc_id:
        return None
    acc, fn = doc_id.split(":", 1)
    return ARCHIVE_URL.format(cik=int(cik), acc=acc.replace("-", ""), fn=fn)


def search(query: str, *, forms: str | None = None, limit: int = MAX_HITS_PER_QUERY
           ) -> list[dict]:
    hits: list[dict] = []
    offset = 0
    while offset < limit:
        params = {"q": query, "from": offset}
        if forms:
            params["forms"] = forms
        data = http.get_json(FTS_URL, params=params)
        if not data:
            break
        page = data.get("hits", {}).get("hits", [])
        if not page:
            break
        hits.extend(page)
        offset += PAGE_SIZE
        if len(page) < PAGE_SIZE:
            break
    return hits[:limit]


def _ingest_filer(conn, hit: dict, query: str) -> bool:
    src = hit.get("_source", {})
    names = src.get("display_names") or []
    if not names:
        return False
    raw = names[0]                       # "ACME WIRE CORP  (CIK 0000123456)"
    name = re.sub(r"\s*\(CIK\s+\d+\)\s*$", "", raw).strip()
    ciks = src.get("ciks") or [""]
    states = src.get("biz_states") or []
    state = states[0] if states else None
    sics = src.get("sics") or []
    url = _parse_id(hit.get("_id", ""), ciks[0]) if ciks[0] else None

    cid, is_new = db.upsert_company(conn, {
        "name": name,
        "state": state,
        "sic_code": sics[0] if sics else None,
        "source": "edgar",
        "institutional_owned": 1,
        "excluded": 1,
        "exclusion_reason": "public SEC filer (institutionally owned)",
    })
    db.add_signal(conn, cid, signal_type="sec_filer",
                  value=f"SEC filer; matched query '{query}'",
                  source="edgar", source_url=url,
                  fetch_date=http.fetched_at(FTS_URL, params={"q": query, "from": 0}),
                  confidence=0.95)
    db.add_signal(conn, cid, signal_type="niche_keyword", value=query,
                  source="edgar", source_url=url, confidence=0.6)
    return is_new


def _mine_competitors(conn, hit: dict, target_states: list[str]) -> int:
    """Fetch a filing doc and extract private company names containing a niche word."""
    src = hit.get("_source", {})
    ciks = src.get("ciks") or [""]
    if not ciks[0]:
        return 0
    url = _parse_id(hit.get("_id", ""), ciks[0])
    if not url:
        return 0
    text = http.get(url)
    if not text:
        return 0

    filer = (src.get("display_names") or [""])[0]
    filer_norm = re.sub(r"\s*\(CIK.*$", "", filer).strip().lower()

    found = 0
    seen: set[str] = set()
    for m in _COMPANY_RE.finditer(text):
        if found >= MAX_MENTIONS_PER_DOC:
            break
        candidate = " ".join(m.group(1).split())
        cl = candidate.lower()
        if cl in seen or len(candidate) < 6:
            continue
        if cl == filer_norm or cl in filer_norm:   # skip the filer itself
            continue
        # Drop matches whose distinctive words are only place names or generic
        # industry/legal tokens (e.g. "Indiana Manufacturing", "Cable Wire").
        core = {w for w in re.sub(r"[^a-z\s]", " ", cl).split()
                if w not in _SUFFIX_TOKENS and w not in _PLACE_WORDS}
        if not core:
            continue
        seen.add(cl)
        cid, _ = db.upsert_company(conn, {
            "name": candidate,
            "source": "edgar",
        })
        db.add_signal(conn, cid, signal_type="competitor_mention",
                      value=f"named in SEC filing by {filer}",
                      source="edgar", source_url=url,
                      fetch_date=http.fetched_at(url), confidence=0.35)
        db.add_signal(conn, cid, signal_type="niche_keyword",
                      value=candidate, source="edgar", source_url=url,
                      confidence=0.4)
        found += 1
    return found


def run(conn, *, queries: list[str], states: list[str], forms: str | None = None,
        mine: bool = True) -> dict:
    print(f"[edgar] full-text search: queries={queries} forms={forms or 'all'}")
    filers_new = 0
    mentions = 0
    all_hits: list[dict] = []
    for q in queries:
        hits = search(q, forms=forms)
        print(f"  '{q}': {len(hits)} filing hits")
        all_hits.extend(hits)
        for h in hits:
            if _ingest_filer(conn, h, q):
                filers_new += 1

    if mine:
        # Mine a capped number of distinct filing docs for competitor names.
        for h in all_hits[:MAX_DOCS_TO_MINE]:
            mentions += _mine_competitors(conn, h, states)
        print(f"  mined {mentions} competitor mentions from "
              f"{min(len(all_hits), MAX_DOCS_TO_MINE)} filings")

    conn.commit()
    notes = (f"{len(all_hits)} filing hits across {len(queries)} queries; "
             f"{filers_new} new public filers (excluded); "
             f"{mentions} competitor mentions captured.")
    db.log_run(conn, "edgar", pulled=len(all_hits), new=filers_new, notes=notes)
    print(f"  {notes}")
    return {"hits": len(all_hits), "filers_new": filers_new, "mentions": mentions}
