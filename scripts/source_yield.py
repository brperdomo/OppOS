#!/usr/bin/env python3
"""Source yield report — which sources actually produce opportunities worth acting on.

Usage:
    python scripts/source_yield.py            # table to stdout
    python scripts/source_yield.py --markdown # markdown table (paste into Slack/Notion)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import oppos.config  # noqa: F401  (loads .env)
from oppos.config import SLACK_ALERT_MIN_SCORE, STAGE2_MIN_SCORE
from oppos.storage.db import _query, init_db

_ACTED = ("qualified", "in_progress", "submitted", "won", "lost")


def fetch_yield() -> list[dict]:
    acted = ", ".join(f"'{s}'" for s in _ACTED)
    rows = _query(f"""
        SELECT source,
               COUNT(*)                                   AS total,
               SUM(fit_score >= {SLACK_ALERT_MIN_SCORE})  AS high_fit,
               SUM(fit_score >= {STAGE2_MIN_SCORE})       AS mid_fit,
               SUM(pipeline_status IN ({acted}))          AS acted,
               SUM(pipeline_status = 'skipped')           AS skipped,
               SUM(pipeline_status = 'expired')           AS expired,
               SUM(lob IS NOT NULL)                       AS routed,
               substr(MIN(created_at), 1, 10)             AS first_seen,
               substr(MAX(created_at), 1, 10)             AS last_seen
        FROM opportunities
        GROUP BY source
        ORDER BY high_fit DESC, mid_fit DESC, total DESC
    """)
    out = []
    for r in rows:  # Turso returns numerics as strings
        out.append({k: (int(v) if k not in ("source", "first_seen", "last_seen") and v is not None else v)
                    for k, v in r.items()})
    return out


def main() -> None:
    init_db()  # applies pending migrations (e.g. the lob column)
    ap = argparse.ArgumentParser()
    ap.add_argument("--markdown", action="store_true")
    args = ap.parse_args()

    rows = fetch_yield()
    cols = ["source", "total", "high_fit", "mid_fit", "acted", "skipped", "expired", "first_seen", "last_seen"]
    heads = ["Source", "Total", f"≥{SLACK_ALERT_MIN_SCORE}", f"≥{STAGE2_MIN_SCORE}", "Acted", "Skipped", "Expired", "First", "Last"]

    if args.markdown:
        print("| " + " | ".join(heads) + " |")
        print("|" + "|".join("---" for _ in heads) + "|")
        for r in rows:
            print("| " + " | ".join(str(r.get(c) if r.get(c) is not None else 0) for c in cols) + " |")
    else:
        print(f"{'source':34} {'total':>6} {'hi':>5} {'mid':>5} {'acted':>6} {'skip':>6} {'exp':>6}  first       last")
        for r in rows:
            print(f"{r['source']:34} {r['total']:>6} {r['high_fit'] or 0:>5} {r['mid_fit'] or 0:>5} "
                  f"{r['acted'] or 0:>6} {r['skipped'] or 0:>6} {r['expired'] or 0:>6}  {r['first_seen']}  {r['last_seen']}")

    total_hi = sum(r["high_fit"] or 0 for r in rows)
    top = rows[0] if rows else None
    if top and total_hi:
        share = 100 * (top["high_fit"] or 0) / total_hi
        print(f"\n{total_hi} high-fit opportunities total; {top['source']} produced {top['high_fit']} ({share:.0f}%).")
    zero = [r["source"] for r in rows if not (r["mid_fit"] or 0) and (r["total"] or 0) >= 10]
    if zero:
        print(f"Sources with ≥10 listings and zero ≥{STAGE2_MIN_SCORE}: {', '.join(zero)}")


if __name__ == "__main__":
    main()
