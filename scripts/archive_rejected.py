"""One-off: move listings the first pass rejected (stored as New, fit 0) to Archive as skipped.

Scans now do this at scan time; this handles the rows stored before that change. Dry run by default.
Run from the repo root against the production env:  python3 scripts/archive_rejected.py [--apply]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import oppos.config  # noqa: E402,F401  (loads .env)
from oppos.storage.db import _query, init_db, set_pipeline_status  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write the changes (default: report only)")
    args = ap.parse_args()
    init_db()
    rows = _query("SELECT source_id, title, fit_score, stage1_json, pipeline_notes FROM opportunities "
                  "WHERE pipeline_status IN ('new', 'expiring_soon') "
                  "AND source_id NOT IN (SELECT source_id FROM pursuits WHERE status IN ('evaluating', 'active', 'submitted'))")
    hits = []
    for r in rows:
        try:
            fit = float(r.get("fit_score") or 0)
            s1 = json.loads(r.get("stage1_json") or "{}") or {}
        except (TypeError, ValueError):
            continue
        notes = str(r.get("pipeline_notes") or "")
        if fit == 0 and s1 and not s1.get("relevant") and (not notes or notes.startswith(("Deadline within", "Auto-"))):
            hits.append((r, str(s1.get("reason") or "not a software fit")[:160]))
    print(f"{len(hits)} listing(s) rejected by the first pass still shown as New")
    for r, reason in hits[:10]:
        print(f"   {r['source_id']:28} {r['title'][:60]}  — {reason[:60]}")
    if not args.apply:
        print("Dry run — re-run with --apply to move them to Archive (skipped).")
        return
    for r, reason in hits:
        set_pipeline_status(r["source_id"], "skipped", notes=f"Set aside by the first pass — {reason}")
    print(f"Moved {len(hits)} to Archive.")


if __name__ == "__main__":
    main()
