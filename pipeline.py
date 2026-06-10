#!/usr/bin/env python3
"""TRS deal sourcing pipeline - command line entry point.

Usage:
    python pipeline.py run                 # full pass: all sources, score, export
    python pipeline.py run --source edgar  # single source, then score + export
    python pipeline.py rescore             # re-apply YAML weights, no re-fetch
    python pipeline.py export              # write Excel from current DB only

Scope flags (apply to `run`):
    --states IL,IN        comma-separated state codes (default: IL,IN)
    --naics 33592,...     comma-separated NAICS codes (default: 33592)
    --query "wire and cable"   repeatable EDGAR full-text query (default: niche set)

Every data source is public and keyless. Responses are cached under cache/ so
re-runs never re-fetch.
"""

from __future__ import annotations

import argparse
import sys
import time

from trs import db, excel, process, settings
from trs.sources import census, edgar

# Default test scope: NAICS 33592 (wire and cable) in Indiana and Illinois.
DEFAULT_STATES = ["IL", "IN"]
DEFAULT_NAICS = ["33592", "335921", "335929"]
DEFAULT_QUERIES = ["wire and cable", "cable assembly", "wire harness"]


def _open():
    conn = db.connect()
    db.init_db(conn)
    return conn


def _run_source(conn, name, *, states, naics, queries, universe_box):
    if name == "edgar":
        edgar.run(conn, queries=queries, states=states)
    elif name == "census":
        info = census.run(conn, states=states, naics_codes=naics)
        info["scope"] = f"NAICS {', '.join(naics)} in {', '.join(states)}"
        universe_box["info"] = info
    else:
        print(f"[pipeline] unknown source: {name}")
        sys.exit(2)


def cmd_run(args):
    states = [s.strip().upper() for s in args.states.split(",") if s.strip()]
    naics = [n.strip() for n in args.naics.split(",") if n.strip()]
    queries = args.query or DEFAULT_QUERIES

    conn = _open()
    db.reset_new_flags(conn)
    universe_box: dict = {}

    sources = [args.source] if args.source else ["census", "edgar"]
    start = time.time()
    for name in sources:
        _run_source(conn, name, states=states, naics=naics,
                    queries=queries, universe_box=universe_box)

    print("[pipeline] applying filters and size estimates")
    process.apply_filters_and_estimates(conn)
    run_id = db.latest_run_id(conn)
    print("[pipeline] scoring")
    n = process.rescore(conn, run_id)
    print(f"  scored {n} companies")

    path = excel.export(conn, universe=universe_box.get("info"))
    print(f"[pipeline] done in {time.time() - start:.1f}s")
    conn.close()
    return path


def cmd_rescore(args):
    conn = _open()
    n = process.rescore(conn)
    print(f"[rescore] rescored {n} companies with current weights")
    excel.export(conn)
    conn.close()


def cmd_export(args):
    conn = _open()
    excel.export(conn)
    conn.close()


def main():
    p = argparse.ArgumentParser(description="TRS deal sourcing pipeline")
    sub = p.add_subparsers(dest="command", required=True)

    pr = sub.add_parser("run", help="full pass or a single source")
    pr.add_argument("--source", choices=["census", "edgar"], default=None)
    pr.add_argument("--states", default=",".join(DEFAULT_STATES))
    pr.add_argument("--naics", default=",".join(DEFAULT_NAICS))
    pr.add_argument("--query", action="append", default=None)
    pr.set_defaults(func=cmd_run)

    sub.add_parser("rescore", help="re-apply YAML weights without re-fetching"
                   ).set_defaults(func=cmd_rescore)
    sub.add_parser("export", help="write Excel from current DB"
                   ).set_defaults(func=cmd_export)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
