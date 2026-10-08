#!/usr/bin/env python3
"""Run the router + scorer against the golden set and report agreement with human decisions.

Run this after any change to prompts, LOB profiles, prefilter rules, or models.

Expectations:
  positive       → fit_score >= STAGE2_MIN_SCORE and recommended_action != "skip"
  negative       → fit_score <  SLACK_ALERT_MIN_SCORE or recommended_action == "skip"
  weak_positive  → reported separately (not counted in the headline numbers)
  lob_expected   → if set, the routed LOB must match

Usage:
    python scripts/eval_scoring.py                 # 30 sampled examples (stratified)
    python scripts/eval_scoring.py --n 80
    python scripts/eval_scoring.py --router-only   # Stage 1 only — cheap sanity check
    python scripts/eval_scoring.py --all           # the whole golden set (costs real tokens)
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import oppos.config  # noqa: F401
from oppos.config import SLACK_ALERT_MIN_SCORE, STAGE2_MIN_SCORE
from oppos.scoring.prefilter import prefilter
from oppos.scoring.qualifier import USAGE, qualify, stage1_filter

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "eval" / "golden_set.jsonl"
RESULTS_DIR = ROOT / "eval" / "results"


def _load() -> list[dict]:
    if not GOLDEN.exists():
        sys.exit("No golden set. Run scripts/build_golden_set.py first.")
    return [json.loads(l) for l in GOLDEN.read_text().splitlines() if l.strip()]


def _sample(examples: list[dict], n: int, seed: int) -> list[dict]:
    random.seed(seed)
    by_label: dict[str, list[dict]] = {}
    for ex in examples:
        by_label.setdefault(ex["label"], []).append(ex)
    out: list[dict] = []
    labels = sorted(by_label)
    per = max(1, n // len(labels))
    for lbl in labels:
        pool = by_label[lbl]
        random.shuffle(pool)
        out += pool[:per]
    return out[:n] if len(out) > n else out


def _expected_ok(label: str, score: int, action: str) -> bool | None:
    if label == "positive":
        return score >= STAGE2_MIN_SCORE and action != "skip"
    if label == "negative":
        return score < SLACK_ALERT_MIN_SCORE or action == "skip"
    return None  # weak_positive — informational


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--router-only", action="store_true")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    examples = _load()
    batch = examples if args.all else _sample(examples, args.n, args.seed)
    print(f"Evaluating {len(batch)} of {len(examples)} examples "
          f"({'router only' if args.router_only else 'router + scorer'})\n")

    results: list[dict] = []
    t0 = time.time()
    for i, ex in enumerate(batch, 1):
        opp = {k: ex.get(k) for k in ("source_id", "source", "title", "agency", "naics_code",
                                     "notice_type", "place_of_performance", "description")}
        prefilter(opp)
        pre_passed = opp["prefilter"]["passed"]
        if not pre_passed:
            score, action, lob, s1 = 0, "skip", None, {"reason": f"prefilter: {opp['prefilter']['reason']}", "lobs": []}
        elif args.router_only:
            s1 = stage1_filter(opp)
            lob = s1["lobs"][0]["lob"] if s1["lobs"] else None
            score = 50 if s1["relevant"] else 0
            action = "investigate" if s1["relevant"] else "skip"
        else:
            qualify(opp)
            s1 = opp["stage1"]
            score = int(opp.get("fit_score") or 0)
            action = opp.get("recommended_action") or "?"
            lob = opp.get("lob")

        ok = _expected_ok(ex["label"], score, action)
        lob_ok = (lob == ex["lob_expected"]) if ex.get("lob_expected") else None
        results.append({"source_id": ex["source_id"], "title": ex["title"][:90], "label": ex["label"],
                        "prefilter_passed": pre_passed, "score": score, "action": action, "lob": lob,
                        "lob_expected": ex.get("lob_expected"), "ok": ok, "lob_ok": lob_ok,
                        "router": s1.get("lobs"), "prior_score": ex.get("fit_score_at_label")})
        flag = "✓" if ok else ("✗" if ok is False else "·")
        print(f"{flag} [{ex['label']:13}] {score:>3} {action:11} {str(lob):9} {ex['title'][:70]}")

    # ── Summary ───────────────────────────────────────────────
    def _rate(lbl: str) -> tuple[int, int]:
        rs = [r for r in results if r["label"] == lbl and r["ok"] is not None]
        return sum(1 for r in rs if r["ok"]), len(rs)

    pos_ok, pos_n = _rate("positive")
    neg_ok, neg_n = _rate("negative")
    weak = [r for r in results if r["label"] == "weak_positive"]
    lob_checked = [r for r in results if r["lob_ok"] is not None]
    lob_dist: dict[str, int] = {}
    for r in results:
        lob_dist[str(r["lob"])] = lob_dist.get(str(r["lob"]), 0) + 1

    print("\n── Summary ──────────────────────────────────────────")
    if pos_n:
        print(f"Positives kept (recall):            {pos_ok}/{pos_n}  ({100 * pos_ok / pos_n:.0f}%)")
    if neg_n:
        print(f"Negatives rejected (no false pos):  {neg_ok}/{neg_n}  ({100 * neg_ok / neg_n:.0f}%)")
    if weak:
        kept = sum(1 for r in weak if r["score"] >= STAGE2_MIN_SCORE and r["action"] != "skip")
        print(f"Weak positives still ≥{STAGE2_MIN_SCORE}:          {kept}/{len(weak)}  (informational)")
    if lob_checked:
        lo = sum(1 for r in lob_checked if r["lob_ok"])
        print(f"LOB routing matches expectation:    {lo}/{len(lob_checked)}")
    print(f"LOB distribution:                   {lob_dist}")
    elapsed = time.time() - t0
    print(f"Calls: {USAGE['calls']}  tokens in/out: {USAGE['input_tokens']}/{USAGE['output_tokens']}  "
          f"time: {elapsed:.0f}s")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / f"eval_{time.strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps({"summary": {"positives": [pos_ok, pos_n], "negatives": [neg_ok, neg_n],
                                           "lob_distribution": lob_dist, "usage": dict(USAGE)},
                               "results": results}, indent=2, ensure_ascii=False))
    print(f"Saved {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
