"""
Master scoring engine.

Scores each company 0-100 across five weighted dimensions and assigns a tier:

    Tier 1 (>= TIER_1_THRESHOLD)  worth Brandon's eyes immediately
    Tier 2 (>= TIER_2_THRESHOLD)  watch list / weekly digest
    Tier 3 (otherwise)            logged, not surfaced

This is a prioritization tool, not a decision tool. All scores are based on
available data; missing data is penalized moderately rather than treated as
disqualifying. The scorer also backfills trs_sector / trs_subsector from the
SIC/NAICS code if a scraper did not set them.
"""

from config import (
    ALL_TARGET_SIC,
    NAICS_TARGET,
    TARGET_STATES,
    PRIORITY_STATES,
    REVENUE_MIN,
    REVENUE_MAX,
    EBITDA_MIN,
    EBITDA_MAX,
    EBITDA_TARGET_MIN,
    EBITDA_TARGET_MAX,
    PREFERRED_REVENUE_MIN,
    PREFERRED_REVENUE_MAX,
    EMPLOYEE_MIN,
    EMPLOYEE_MAX,
    WEIGHT_SECTOR_FIT,
    WEIGHT_GEOGRAPHY,
    WEIGHT_SIZE_FIT,
    WEIGHT_OWNERSHIP_SIGNAL,
    WEIGHT_STRESS_SIGNAL,
    TIER_1_THRESHOLD,
    TIER_2_THRESHOLD,
)
from scoring.sector_map import classify
from scoring.signals import ownership_score, stress_score

# Precompute 3-char prefixes once.
_SIC_PREFIXES = {str(c)[:3] for c in ALL_TARGET_SIC}
_NAICS_PREFIXES = {str(c)[:3] for c in NAICS_TARGET}


class Scorer:
    def score(self, company: dict) -> dict:
        company = dict(company)  # never mutate the caller's dict

        # Backfill sector classification if the scraper didn't provide it.
        if not company.get("trs_sector"):
            company.update(
                classify(company.get("sic_code"), company.get("naics_code"))
            )

        s_sector = self._score_sector(company)
        s_geo = self._score_geography(company)
        s_size = self._score_size(company)
        s_ownership = ownership_score(company)
        s_stress = stress_score(company)

        total = round(
            s_sector * WEIGHT_SECTOR_FIT / 100
            + s_geo * WEIGHT_GEOGRAPHY / 100
            + s_size * WEIGHT_SIZE_FIT / 100
            + s_ownership * WEIGHT_OWNERSHIP_SIGNAL / 100
            + s_stress * WEIGHT_STRESS_SIGNAL / 100
        )

        if total >= TIER_1_THRESHOLD:
            tier = 1
        elif total >= TIER_2_THRESHOLD:
            tier = 2
        else:
            tier = 3

        company.update(
            score_sector=s_sector,
            score_geography=s_geo,
            score_size=s_size,
            score_ownership=s_ownership,
            score_stress=s_stress,
            score_total=total,
            tier=tier,
        )
        return company

    def _score_sector(self, c) -> int:
        sic = str(c.get("sic_code") or "")
        naics = str(c.get("naics_code") or "")
        if sic and sic[:3] in _SIC_PREFIXES:
            return 100
        if naics and naics[:3] in _NAICS_PREFIXES:
            return 90
        if c.get("trs_sector") in ("Manufacturing", "Distribution", "Services"):
            return 70
        return 20  # Unknown sector — penalize but don't eliminate.

    def _score_geography(self, c) -> int:
        state = (c.get("state") or "").upper()
        if not state:
            return 40  # Unknown location — moderate penalty.
        if state in PRIORITY_STATES:
            return 100
        if state in TARGET_STATES:
            return 75
        return 30  # Non-target state — low priority.

    def _score_size(self, c) -> int:
        """Peak score for the current focus band; full Fund III range scores lower.

        EBITDA is the best size signal when present. When it is not (most
        records), revenue stands in for it via the PREFERRED_REVENUE_* band,
        which is the focus EBITDA band converted at assumed margins.
        """
        ebitda = c.get("ebitda_estimate")
        if ebitda:
            return self._score_ebitda(ebitda)

        rev_low = c.get("revenue_estimate_low") or c.get("listed_revenue")
        rev_high = c.get("revenue_estimate_high")
        if rev_low and rev_high:
            return self._score_revenue_band(rev_low, rev_high)
        if rev_low:
            return self._score_revenue_point(rev_low)

        employees_high = c.get("employee_count_high")
        if employees_high:
            if EMPLOYEE_MIN <= employees_high <= EMPLOYEE_MAX:
                return 70
            if employees_high < EMPLOYEE_MAX * 2:
                return 40

        return 30  # Insufficient size data.

    @staticmethod
    def _score_ebitda(ebitda) -> int:
        if EBITDA_TARGET_MIN <= ebitda <= EBITDA_TARGET_MAX:
            return 100  # current focus band
        if EBITDA_MIN <= ebitda <= EBITDA_MAX:
            return 55  # within Fund III criteria, outside current focus
        return 15  # outside Fund III criteria entirely

    @staticmethod
    def _score_revenue_band(rev_low, rev_high) -> int:
        def overlaps(lo, hi):
            return min(rev_high, hi) - max(rev_low, lo) > 0

        if overlaps(PREFERRED_REVENUE_MIN, PREFERRED_REVENUE_MAX):
            return 100  # straddles the focus band
        if overlaps(REVENUE_MIN, REVENUE_MAX):
            return 55  # within Fund III range, outside focus
        gap = min(abs(rev_low - REVENUE_MAX), abs(rev_high - REVENUE_MIN))
        return 40 if gap < 2_000_000 else 20

    @staticmethod
    def _score_revenue_point(rev) -> int:
        if PREFERRED_REVENUE_MIN <= rev <= PREFERRED_REVENUE_MAX:
            return 100
        if REVENUE_MIN <= rev <= REVENUE_MAX:
            return 55
        if rev < REVENUE_MAX * 1.5:
            return 35
        return 20
