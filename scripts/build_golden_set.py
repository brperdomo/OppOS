#!/usr/bin/env python3
"""Build the scoring golden set from human decisions already in the database.

Labels come from pipeline_status, i.e. what a human actually decided:
  positive  — qualified, in_progress, submitted, won, lost (pursued, whatever the outcome)
  negative  — skipped (someone looked and passed)

Model scores are NOT used as labels (that would be circular). Pass
--include-high-fit to add fit>=80 "new" rows as `weak_positive` for coverage;
they are reported separately by eval_scoring.py.

Output: eval/golden_set.jsonl — one JSON object per line. Hand-edit freely:
add `label`, `lob_expected`, and `note` fields; rows are keyed by source_id.

Usage:
    python scripts/build_golden_set.py
    python scripts/build_golden_set.py --include-high-fit --max-negatives 150
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import oppos.config  # noqa: F401
from oppos.storage.db import _query, init_db

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "eval" / "golden_set.jsonl"

_POS = ("qualified", "in_progress", "submitted", "won", "lost")


def _row_to_example(r: dict, label: str) -> dict:
    return {
        "source_id": r["source_id"],
        "source": r.get("source"),
        "title": r.get("title") or "",
        "agency": r.get("agency") or "",
        "naics_code": r.get("naics_code") or "",
        "notice_type": r.get("notice_type") or "",
        "place_of_performance": r.get("place_of_performance") or "",
        "description": (r.get("description") or "")[:4000],
        "label": label,
        "label_source": f"pipeline_status:{r.get('pipeline_status')}",
        "fit_score_at_label": int(r.get("fit_score") or 0),
        "lob_at_label": r.get("lob"),
        "lob_expected": None,
        "note": "",
    }


def main() -> None:
    init_db()  # applies pending migrations (e.g. the lob column)
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-negatives", type=int, default=120)
    ap.add_argument("--include-high-fit", action="store_true")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    random.seed(args.seed)

    existing: dict[str, dict] = {}
    if OUT.exists():
        for line in OUT.read_text().splitlines():
            if line.strip():
                ex = json.loads(line)
                existing[ex["source_id"]] = ex

    pos_ph = ", ".join("?" for _ in _POS)
    positives = _query(f"SELECT * FROM opportunities WHERE pipeline_status IN ({pos_ph})", _POS)
    negatives = _query("SELECT * FROM opportunities WHERE pipeline_status = 'skipped'")
    random.shuffle(negatives)
    negatives = negatives[: args.max_negatives]

    examples = [_row_to_example(r, "positive") for r in positives]
    examples += [_row_to_example(r, "negative") for r in negatives]

    if args.include_high_fit:
        hi = _query("SELECT * FROM opportunities WHERE pipeline_status = 'new' AND fit_score >= 80")
        examples += [_row_to_example(r, "weak_positive") for r in hi]

    # Preserve hand edits on rows that already exist.
    merged = 0
    for ex in examples:
        prev = existing.get(ex["source_id"])
        if prev:
            for k in ("label", "lob_expected", "note"):
                if prev.get(k) not in (None, ""):
                    ex[k] = prev[k]
            merged += 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w") as f:
        for ex in examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    counts: dict[str, int] = {}
    for ex in examples:
        counts[ex["label"]] = counts.get(ex["label"], 0) + 1
    print(f"Wrote {len(examples)} examples to {OUT.relative_to(ROOT)}  ({counts}; {merged} kept hand edits)")
    if counts.get("positive", 0) < 10:
        print("WARNING: very few positives — eval will mostly measure false-positive rate. "
              "Add hand-labeled positives (label='positive', optionally lob_expected) to the file.")


if __name__ == "__main__":
    main()
