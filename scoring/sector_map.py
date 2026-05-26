"""
SIC / NAICS to TRS sector classification.

TRS targets three sectors: Manufacturing, Distribution, and B2B Services.
`classify()` maps a raw SIC and/or NAICS code onto a (sector, subsector)
label used for scoring and for the Excel/digest output. Matching is done on
code prefixes so any 4-digit SIC under a known family is captured.
"""

# SIC prefix -> (sector, subsector). Most specific prefixes first.
_SIC_RULES = [
    ("346", ("Manufacturing", "Fabricated Metal")),
    ("347", ("Manufacturing", "Fabricated Metal")),
    ("348", ("Manufacturing", "Fabricated Metal")),
    ("349", ("Manufacturing", "Fabricated Metal")),
    ("351", ("Manufacturing", "Industrial Machinery")),
    ("352", ("Manufacturing", "Industrial Machinery")),
    ("353", ("Manufacturing", "Industrial Machinery")),
    ("354", ("Manufacturing", "Industrial Machinery")),
    ("355", ("Manufacturing", "Industrial Machinery")),
    ("356", ("Manufacturing", "Industrial Machinery")),
    ("357", ("Manufacturing", "Industrial Machinery")),
    ("361", ("Manufacturing", "Electrical / Electronics")),
    ("362", ("Manufacturing", "Electrical / Electronics")),
    ("363", ("Manufacturing", "Electrical / Electronics")),
    ("364", ("Manufacturing", "Electrical / Electronics")),
    ("366", ("Manufacturing", "Electrical / Electronics")),
    ("367", ("Manufacturing", "Electrical / Electronics")),
    ("305", ("Manufacturing", "Plastics / Rubber")),
    ("306", ("Manufacturing", "Plastics / Rubber")),
    ("307", ("Manufacturing", "Plastics / Rubber")),
    ("308", ("Manufacturing", "Plastics / Rubber")),
    ("331", ("Manufacturing", "Primary Metals")),
    ("332", ("Manufacturing", "Primary Metals")),
    ("333", ("Manufacturing", "Primary Metals")),
    ("335", ("Manufacturing", "Primary Metals")),
    ("336", ("Manufacturing", "Primary Metals")),
    ("381", ("Manufacturing", "Instruments")),
    ("382", ("Manufacturing", "Instruments")),
    ("504", ("Distribution", "Durable Goods Wholesale")),
    ("506", ("Distribution", "Electrical Apparatus")),
    ("507", ("Distribution", "Hardware / Plumbing")),
    ("508", ("Distribution", "Industrial Machinery & Equipment")),
    ("509", ("Distribution", "Durable Goods Wholesale")),
    ("738", ("Services", "Industrial / Building Services")),
    ("769", ("Services", "Repair Services")),
    ("871", ("Services", "Engineering")),
    ("899", ("Services", "Technical Services")),
]

# NAICS prefix -> (sector, subsector).
_NAICS_RULES = [
    ("332", ("Manufacturing", "Fabricated Metal")),
    ("333", ("Manufacturing", "Machinery")),
    ("334", ("Manufacturing", "Computer / Electronic")),
    ("335", ("Manufacturing", "Electrical Equipment")),
    ("336", ("Manufacturing", "Transportation Equipment")),
    ("339", ("Manufacturing", "Miscellaneous")),
    ("423", ("Distribution", "Durable Goods Wholesale")),
    ("424", ("Distribution", "Nondurable Goods Wholesale")),
    ("541330", ("Services", "Engineering")),
    ("541614", ("Services", "Logistics Consulting")),
    ("541", ("Services", "Professional / Technical")),
    ("811", ("Services", "Repair & Maintenance")),
]


def _match(code, rules):
    code = (str(code) if code is not None else "").strip()
    if not code:
        return None
    # Try longest prefixes first so 541330 beats 541.
    for prefix, label in sorted(rules, key=lambda r: -len(r[0])):
        if code.startswith(prefix):
            return label
    return None


def classify(sic_code=None, naics_code=None):
    """Return {'trs_sector': ..., 'trs_subsector': ...}.

    Unmapped codes yield (None, None) so the caller can decide how to handle
    an unknown sector.
    """
    label = _match(sic_code, _SIC_RULES) or _match(naics_code, _NAICS_RULES)
    if not label:
        return {"trs_sector": None, "trs_subsector": None}
    sector, subsector = label
    return {"trs_sector": sector, "trs_subsector": subsector}
