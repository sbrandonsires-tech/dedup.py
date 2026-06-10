"""Company-website crawl - founding year, family language, owner names.

The highest-value succession signals live on a company's own About / History /
Team pages. This source:
  1. takes candidate companies from config/seeds.yaml (analyst-maintained) and
     from any DB company that already has a domain;
  2. resolves a domain when missing by guessing from the name and verifying the
     page actually belongs to the company (fully keyless - no search API);
  3. crawls a small set of About/History/Team paths (polite, cached);
  4. extracts founded year, family-ownership language, generational-transition
     language, and owner names + titles, writing each as a sourced signal.

Sites behind bot protection (Cloudflare 202/503) are skipped gracefully.
"""

from __future__ import annotations

import re
from datetime import date

import yaml
from bs4 import BeautifulSoup

from .. import db, http, normalize, settings

SEEDS_PATH = settings.CONFIG_DIR / "seeds.yaml"
THIS_YEAR = date.today().year

ABOUT_PATHS = [
    "/about/", "/about-us/", "/about", "/about-us",
    "/our-history/", "/history/", "/our-story/", "/company/",
    "/who-we-are/", "/team/", "/leadership/", "/our-team/", "/",
]
MAX_PAGES = 6

_YEAR = r"((?:18|19|20)\d\d)"
_FOUNDED_RE = [
    re.compile(rf"(?:founded|established|est\.?|in business since|"
               rf"proudly serving since|serving .{{0,30}}? since|since)\s*"
               rf"(?:in\s+)?{_YEAR}", re.I),
    re.compile(rf"{_YEAR}\s*[-:]?\s*(?:founded|established)", re.I),
]
_FAMILY_RE = re.compile(
    r"family[\s\-]?(?:owned(?:\s+and\s+operated)?|run|operated|business|"
    r"owned)", re.I)
_GEN_RE = re.compile(
    r"((?:second|third|fourth|fifth|2nd|3rd|4th|5th)[\s\-]generation|"
    r"\b\d(?:st|nd|rd|th)[\s\-]generation)", re.I)
_OWNER_RE = [
    re.compile(r"([A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-zA-Z\-']+)\s*[,\-]?\s*"
               r"(President(?:\s*&\s*CEO)?|Chief Executive Officer|CEO|Owner|"
               r"Co[\-\s]?Founder|Founder|Principal|Chairman|Managing Partner)\b"),
    re.compile(r"\b(President|CEO|Owner|Founder|Chairman)\b\s*[:\-]?\s*"
               r"([A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-zA-Z\-']+)"),
]
_TITLES = {"president", "ceo", "owner", "founder", "co-founder", "chairman",
           "principal", "managing partner", "chief executive officer",
           "president & ceo"}


def _slug_candidates(name: str) -> list[str]:
    norm = normalize.normalize_name(name)        # suffix-stripped, lowercased
    if not norm:
        return []
    words = norm.split()
    joined = "".join(words)
    hyphen = "-".join(words)
    initials = "".join(w[0] for w in words)
    bases = {joined, hyphen}
    if len(words) > 1:
        bases.add(joined[:18])
    if len(initials) >= 3:
        bases.add(initials)
    out = []
    for b in bases:
        out += [f"{b}.com", f"{b}.net"]
    return out


def _page_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return soup.get_text(" ", strip=True)


def _verify(domain: str, name: str) -> bool:
    html = http.get(f"https://{domain}/")
    if not html:
        return False
    text = _page_text(html).lower()
    tokens = [w for w in normalize.normalize_name(name).split() if len(w) > 3]
    if not tokens:
        return True
    hits = sum(1 for t in tokens if t in text)
    return hits >= max(1, len(tokens) // 2)


def _discover_domain(name: str, hint: str | None) -> str | None:
    if hint:
        return normalize.normalize_domain(hint)
    for cand in _slug_candidates(name):
        if _verify(cand, name):
            return cand
    return None


def _extract(text: str) -> dict:
    years = []
    for rx in _FOUNDED_RE:
        for m in rx.finditer(text):
            y = int(m.group(1))
            if 1850 <= y <= THIS_YEAR:
                years.append(y)
    founded = min(years) if years else None

    family = bool(_FAMILY_RE.search(text))
    gen_m = _GEN_RE.search(text)
    generation = " ".join(gen_m.group(1).split()) if gen_m else None

    owners: list[tuple[str, str]] = []
    seen = set()
    for rx in _OWNER_RE:
        for m in rx.finditer(text):
            a, b = m.group(1), m.group(2)
            # Order the (name, title) pair regardless of which regex matched.
            if a.lower() in _TITLES:
                title, person = a, b
            else:
                person, title = a, b
            person = " ".join(person.split())
            if person.lower() in seen or len(person.split()) < 2:
                continue
            # Reject obvious non-names (all-caps headings, single words).
            if any(w.isupper() and len(w) > 3 for w in person.split()):
                continue
            seen.add(person.lower())
            owners.append((person, " ".join(title.split())))
            if len(owners) >= 5:
                break
    return {"founded": founded, "family": family, "generation": generation,
            "owners": owners}


def _crawl(domain: str) -> list[tuple[str, str]]:
    pages = []
    for path in ABOUT_PATHS:
        if len(pages) >= MAX_PAGES:
            break
        html = http.get(f"https://{domain}{path}")
        if html:
            pages.append((f"https://{domain}{path}", _page_text(html)))
    return pages


def _process_company(conn, name: str, state: str | None, domain_hint: str | None) -> dict:
    domain = _discover_domain(name, domain_hint)
    if not domain:
        print(f"  [website] no resolvable domain: {name}")
        return {"resolved": False}

    pages = _crawl(domain)
    if not pages:
        print(f"  [website] {domain}: no crawlable pages (likely bot-protected)")
        # Still record the company with its domain for later.
        db.upsert_company(conn, {"name": name, "state": state,
                                 "domain": domain, "source": "website"})
        return {"resolved": True, "crawled": False, "domain": domain}

    combined = " ".join(t for _, t in pages)
    info = _extract(combined)
    cite = pages[0][0]
    fetch_date = http.fetched_at(f"https://{domain}/")

    record = {"name": name, "state": state, "domain": domain, "source": "website"}
    if info["founded"]:
        record["founded_year"] = info["founded"]
        record["years_in_business"] = THIS_YEAR - info["founded"]
    cid, _ = db.upsert_company(conn, record)

    if info["founded"]:
        db.add_signal(conn, cid, signal_type="founded_year",
                      value=str(info["founded"]), source="website",
                      source_url=cite, fetch_date=fetch_date, confidence=0.8)
    if info["family"]:
        db.add_signal(conn, cid, signal_type="family_owned",
                      value="family ownership language on site", source="website",
                      source_url=cite, fetch_date=fetch_date, confidence=0.75)
    if info["generation"]:
        db.add_signal(conn, cid, signal_type="generation",
                      value=info["generation"], source="website",
                      source_url=cite, fetch_date=fetch_date, confidence=0.75)
    for person, title in info["owners"]:
        db.add_contact(conn, cid, name=person, title=title, source="website",
                       source_url=cite, fetch_date=fetch_date)
        db.add_signal(conn, cid, signal_type="owner_named",
                      value=f"{person} - {title}", source="website",
                      source_url=cite, fetch_date=fetch_date, confidence=0.7)

    print(f"  [website] {domain}: founded={info['founded']} "
          f"family={info['family']} gen={info['generation']} "
          f"owners={len(info['owners'])}")
    return {"resolved": True, "crawled": True, "domain": domain,
            "company_id": cid, **info}


def _load_seeds() -> list[dict]:
    if not SEEDS_PATH.exists():
        return []
    with open(SEEDS_PATH, "r", encoding="utf-8") as fh:
        return (yaml.safe_load(fh) or {}).get("seeds", []) or []


def run(conn, *, use_db_domains: bool = True) -> dict:
    print("[website] crawling seed companies and DB companies with domains")
    processed = resolved = crawled = 0

    for seed in _load_seeds():
        processed += 1
        r = _process_company(conn, seed["name"], seed.get("state"),
                             seed.get("domain"))
        resolved += int(r.get("resolved", False))
        crawled += int(r.get("crawled", False))

    if use_db_domains:
        rows = conn.execute(
            "SELECT name, state, domain FROM companies "
            "WHERE domain IS NOT NULL AND domain != '' AND excluded = 0"
        ).fetchall()
        for row in rows:
            processed += 1
            r = _process_company(conn, row["name"], row["state"], row["domain"])
            resolved += int(r.get("resolved", False))
            crawled += int(r.get("crawled", False))

    conn.commit()
    notes = f"{processed} companies processed; {resolved} domains resolved; {crawled} crawled."
    db.log_run(conn, "website", pulled=processed, new=crawled, notes=notes)
    print(f"  {notes}")
    return {"processed": processed, "resolved": resolved, "crawled": crawled}
