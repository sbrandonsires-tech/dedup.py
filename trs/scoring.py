"""Scoring engine. Produces a 0-100 total from five weighted components.

Each component is computed on its own 0-100 sub-scale, then weighted per
config/weights.yaml and summed. Every run stores the full component breakdown
(scores.breakdown_json) so any total is auditable and reproducible.
"""

from __future__ import annotations

import json
from typing import Any

from . import settings


def _niche_fit(company: dict, signals: list[dict], tgt: dict) -> tuple[float, list[str]]:
    """Best niche match across company name, NAICS, and text signals."""
    notes: list[str] = []
    haystacks = [
        (company.get("name") or "").lower(),
        (company.get("naics_label") or "").lower(),
    ]
    haystacks += [
        (s.get("value") or "").lower()
        for s in signals if s.get("signal_type") == "niche_keyword"
    ]
    blob = " ".join(haystacks)

    best = 0.0
    niches = tgt.get("niches", {})
    for group_name, group in niches.items():
        weight = float(group.get("weight", 0))
        for kw in group.get("keywords", []):
            if kw.lower() in blob:
                if weight > best:
                    best = weight
                notes.append(f"{group_name} niche match: '{kw}'")
                break

    # NAICS-based lift: a priority NAICS code guarantees a strong niche floor.
    naics = (company.get("naics_code") or "")
    naics_cfg = tgt.get("naics", {})
    if any(naics.startswith(p) for p in naics_cfg.get("priority", [])):
        best = max(best, 90.0)
        notes.append(f"priority NAICS {naics}")
    elif any(naics.startswith(c) for c in naics_cfg.get("core", [])):
        best = max(best, 60.0)
        notes.append(f"core NAICS {naics}")

    if not notes:
        notes.append("no niche keyword or NAICS match")
    return best, notes


def _size_fit(company: dict, tgt: dict) -> tuple[float, list[str]]:
    size = tgt.get("size", {})
    notes: list[str] = []

    emp = company.get("employee_count")
    rev = company.get("revenue_estimate")

    # Estimate revenue from headcount when no financials are present.
    if rev in (None, 0) and emp:
        rev = emp * float(size.get("revenue_per_employee", 250000))
        notes.append(f"revenue estimated from {emp} employees")

    def band_score(val, lo, hi):
        if val is None:
            return None
        if lo <= val <= hi:
            return 100.0
        # Linear taper to 0 at 2x distance below lo / above hi.
        if val < lo:
            return max(0.0, 100.0 * (val / lo))
        return max(0.0, 100.0 * (1 - (val - hi) / hi))

    scores = []
    if emp is not None:
        s = band_score(emp, size.get("employee_min", 10), size.get("employee_max", 250))
        scores.append(s)
        notes.append(f"{emp} employees")
    if rev is not None:
        s = band_score(rev, size.get("revenue_min"), size.get("revenue_max"))
        scores.append(s)
        notes.append(f"revenue ~${rev:,.0f}")

    if not scores:
        notes.append("no size data")
        return 0.0, notes
    return sum(scores) / len(scores), notes


def _succession(company: dict, signals: list[dict], tgt: dict) -> tuple[float, list[str]]:
    notes: list[str] = []
    score = 0.0

    years = company.get("years_in_business")
    founded = company.get("founded_year")
    if years is None and founded:
        years = 2025 - int(founded)
    if years is not None:
        if years >= 20:
            score += 35
            notes.append(f"{years} yr operating history (20+)")
        elif years >= 10:
            score += 18
            notes.append(f"{years} yr operating history")

    age = company.get("owner_age_estimate")
    if age is not None and age >= 60:
        score += 35
        notes.append(f"owner age ~{age} (60+)")

    sig_types = {s.get("signal_type") for s in signals}
    sig_values = " ".join((s.get("value") or "").lower() for s in signals)
    if "family_owned" in sig_types or "family owned" in sig_values \
            or "generation" in sig_values:
        score += 20
        notes.append("family / generational ownership language")
    if "retirement" in sig_values or "succession" in sig_values:
        score += 15
        notes.append("retirement / succession language")

    if company.get("institutional_owned"):
        score = 0.0
        notes = ["institutional ownership detected (no succession opportunity)"]

    if not notes:
        notes.append("no succession signals found")
    return min(score, 100.0), notes


def _geography(company: dict, tgt: dict) -> tuple[float, list[str]]:
    state = (company.get("state") or "").upper()
    geo = tgt.get("geography", {}).get("tiers", {})
    for tier_name, tier in geo.items():
        if tier_name == "default_weight":
            continue
        if state in [s.upper() for s in tier.get("states", [])]:
            return float(tier.get("weight", 0)), [f"{state} in {tier_name} tier"]
    default = float(tgt.get("geography", {}).get("tiers", {}).get("default_weight", 30))
    return default, [f"{state or 'unknown'} not in a priority tier"]


def _data_confidence(signals: list[dict]) -> tuple[float, list[str]]:
    cited = [s for s in signals if s.get("source_url")]
    distinct_sources = {s.get("source") for s in signals}
    # Confidence rises with corroboration: more cited signals, more sources.
    score = min(100.0, 25.0 * len(distinct_sources) + 5.0 * len(cited))
    notes = [f"{len(signals)} signals, {len(cited)} cited, "
             f"{len(distinct_sources)} distinct source(s)"]
    return score, notes


def score_company(company: dict, signals: list[dict]) -> dict[str, Any]:
    w = settings.weights()["weights"]
    tgt = settings.targets()

    niche, niche_notes = _niche_fit(company, signals, tgt)
    size, size_notes = _size_fit(company, tgt)
    succ, succ_notes = _succession(company, signals, tgt)
    geo, geo_notes = _geography(company, tgt)
    conf, conf_notes = _data_confidence(signals)

    weighted = {
        "niche_fit": niche * w["niche_fit"] / 100,
        "size_fit": size * w["size_fit"] / 100,
        "succession": succ * w["succession"] / 100,
        "geography": geo * w["geography"] / 100,
        "data_confidence": conf * w["data_confidence"] / 100,
    }
    total = round(sum(weighted.values()), 1)

    breakdown = {
        "total": total,
        **{k: round(v, 1) for k, v in weighted.items()},
        "json": json.dumps({
            "weights": w,
            "subscores": {
                "niche_fit": round(niche, 1),
                "size_fit": round(size, 1),
                "succession": round(succ, 1),
                "geography": round(geo, 1),
                "data_confidence": round(conf, 1),
            },
            "weighted": {k: round(v, 1) for k, v in weighted.items()},
            "rationale": {
                "niche_fit": niche_notes,
                "size_fit": size_notes,
                "succession": succ_notes,
                "geography": geo_notes,
                "data_confidence": conf_notes,
            },
        }, indent=None),
    }
    return breakdown
