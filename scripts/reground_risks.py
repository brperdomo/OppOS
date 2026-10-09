#!/usr/bin/env python3
"""Re-ground stored assessments without calling the model.

Applies the same rule the scorer now enforces — a risk must quote the RFP, and
speculative or unquoted risks are knowledge gaps — to `stage2_json` already in
the database. No API calls; scores are not changed.

Usage:
    python scripts/reground_risks.py            # dry run: counts what would move
    python scripts/reground_risks.py --apply    # rewrite stage2_json in place
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import oppos.config  # noqa: F401
from oppos.scoring.qualifier import _ground_risks
from oppos.scoring.schema import normalize_points
from oppos.storage.db import _execute, _query, init_db


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write changes (default is a dry run)")
    args = ap.parse_args()
    init_db()

    rows = _query("SELECT source_id, title, description, attachment_text, stage2_json FROM opportunities WHERE stage2_json IS NOT NULL AND stage2_json != ''")
    touched = moved = legacy = 0
    examples: list[str] = []
    for r in rows:
        try:
            s2 = json.loads(r["stage2_json"])
        except (TypeError, json.JSONDecodeError):
            continue
        raw_risks = s2.get("risks") or []
        if not raw_risks or any(not isinstance(x, dict) for x in raw_risks):
            legacy += 1  # pre-evidence-schema assessment (plain-string risks) — leave as is
            continue
        risks = normalize_points(raw_risks)
        gaps = [str(g).strip() for g in (s2.get("knowledge_gaps") or []) if str(g).strip()]
        corpus = "\n".join(str(r.get(k) or "") for k in ("title", "description", "attachment_text"))
        kept, new_gaps = _ground_risks(risks, list(gaps), title=str(r.get("title") or ""), corpus=corpus)
        n_moved = len(risks) - len(kept)
        if not n_moved:
            continue
        touched += 1
        moved += n_moved
        if len(examples) < 5:
            examples.append(next(x["claim"] for x in risks if x not in kept)[:110])
        if args.apply:
            s2["risks"], s2["knowledge_gaps"] = kept, new_gaps[:12]
            _execute("UPDATE opportunities SET stage2_json = ? WHERE source_id = ?",
                     (json.dumps(s2, ensure_ascii=False), r["source_id"]))

    verb = "Rewrote" if args.apply else "Would rewrite"
    print(f"{verb} {touched} of {len(rows) - legacy} evidence-schema assessments, moving {moved} speculative risk(s) to knowledge gaps "
          f"({legacy} legacy assessments with plain-string risks left untouched — re-score to upgrade them).")
    for e in examples:
        print("  e.g.", e)
    if not args.apply and touched:
        print("Run with --apply to write.")


if __name__ == "__main__":
    main()
