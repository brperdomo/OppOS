"""One-off: retire every stored Starbridge listing and push pending status changes to Notion.

The Starbridge connector was removed from the code in PR #2; its stored rows (303 still active) were never
retired, so they dominated the active list and carried their own duplicates. This script

  1. marks every active Starbridge row expired (note explains why) and flags rows that have a Notion page,
  2. pushes the Pipeline Status + Notes of every notion_dirty row (those Starbridge rows plus the Rhode Island
     rows the re-sync expired) to Notion and clears the flag on success,
  3. clears the now-meaningless `excluded_sources` entry.

Run from the repo root against the production env:  python scripts/retire_starbridge.py [--dry-run]
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import oppos.config  # noqa: E402,F401  (loads .env)
from oppos.outputs.notion_sync import update_pipeline_status  # noqa: E402
from oppos.storage.db import _execute, _query, clear_notion_dirty, init_db, set_meta  # noqa: E402

ACTIVE = ("new", "qualified", "expiring_soon", "in_progress")
NOTE = "Retired — Starbridge connector removed (aggregator listings were unreliable / duplicated)"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    init_db()
    ph = ", ".join("?" for _ in ACTIVE)

    active = _query(f"SELECT count(*) c FROM opportunities WHERE source='starbridge' AND pipeline_status IN ({ph})", ACTIVE)[0]["c"]
    print(f"Starbridge rows to retire: {active}")
    if not args.dry_run:
        _execute(
            f"UPDATE opportunities SET pipeline_status='expired', pipeline_notes=?, pipeline_updated_at=?, "
            f"notion_dirty = CASE WHEN notion_page_id IS NOT NULL AND notion_page_id != '' THEN 1 ELSE notion_dirty END "
            f"WHERE source='starbridge' AND pipeline_status IN ({ph})",
            (NOTE, datetime.now(timezone.utc).replace(tzinfo=None).isoformat(), *ACTIVE),
        )
        set_meta("excluded_sources", "[]")

    dirty = _query("SELECT source_id, pipeline_status, pipeline_notes FROM opportunities "
                   "WHERE notion_dirty=1 AND notion_page_id IS NOT NULL AND notion_page_id != ''")
    print(f"Notion pages to update: {len(dirty)}" + (" (dry run — not pushed)" if args.dry_run else ""))
    if args.dry_run:
        return
    ok = fail = 0
    for r in dirty:
        try:
            if update_pipeline_status(r["source_id"], r["pipeline_status"], notes=r["pipeline_notes"] or ""):
                clear_notion_dirty(r["source_id"])
                ok += 1
            else:
                fail += 1
        except Exception as e:  # keep going; the row stays dirty and the next pipeline run retries it
            fail += 1
            print(f"  failed {r['source_id']}: {str(e)[:120]}")
        time.sleep(0.35)  # Notion rate limit (~3 req/s)
    print(f"Notion: {ok} updated, {fail} failed (failed rows stay notion_dirty and retry on the next pipeline run)")
    print("Active rows by source:",
          [(r["source"], r["c"]) for r in _query(f"SELECT source, count(*) c FROM opportunities WHERE pipeline_status IN ({ph}) "
                                                 f"GROUP BY source ORDER BY c DESC", ACTIVE)])


if __name__ == "__main__":
    main()
