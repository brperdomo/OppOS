"""One-off: retire every stored Starbridge listing and push pending status changes to Notion.

The Starbridge connector was removed from the code in PR #2; its stored rows (303 still active) were never
retired, so they dominated the active list and carried their own duplicates. This script

  1. marks every active, unclaimed Starbridge row expired (note explains why) and flags rows that have a
     Notion page — rows with an open pursuit (claimed / pursuing) are left alone, as `archive_sources` does,
  2. re-syncs every notion_dirty row's page with the full stored row (status, notes and any refreshed listing
     metadata), the same path the scheduled pipeline retries, clearing the flag only when the push succeeded,
  3. drops `starbridge` from `excluded_sources`, leaving any other excluded source in place.

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
from oppos.outputs.notion_sync import push_opportunity  # noqa: E402
from oppos.storage.db import (_execute, _query, clear_notion_dirty, get_excluded_sources, init_db, row_to_opp,  # noqa: E402
                              set_excluded_sources)

ACTIVE = ("new", "qualified", "expiring_soon")  # in_progress rows are claimed: never retired here
OPEN_PURSUIT = "SELECT source_id FROM pursuits WHERE status IN ('evaluating', 'active')"
NOTE = "Retired — Starbridge connector removed (aggregator listings were unreliable / duplicated)"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    init_db()
    ph = ", ".join("?" for _ in ACTIVE)

    where = f"source='starbridge' AND pipeline_status IN ({ph}) AND source_id NOT IN ({OPEN_PURSUIT})"
    active = _query(f"SELECT count(*) c FROM opportunities WHERE {where}", ACTIVE)[0]["c"]
    claimed = _query(f"SELECT count(*) c FROM opportunities WHERE source='starbridge' AND pipeline_status IN ({ph}) "
                     f"AND source_id IN ({OPEN_PURSUIT})", ACTIVE)[0]["c"]
    print(f"Starbridge rows to retire: {active} (left alone — open pursuit: {claimed})")
    if not args.dry_run:
        _execute(
            f"UPDATE opportunities SET pipeline_status='expired', pipeline_notes=?, pipeline_updated_at=?, "
            f"notion_dirty = CASE WHEN notion_page_id IS NOT NULL AND notion_page_id != '' THEN 1 ELSE notion_dirty END "
            f"WHERE {where}",
            (NOTE, datetime.now(timezone.utc).replace(tzinfo=None).isoformat(), *ACTIVE),
        )
        set_excluded_sources([s for s in get_excluded_sources() if s != "starbridge"])

    dirty = _query("SELECT * FROM opportunities WHERE notion_dirty=1 AND notion_page_id IS NOT NULL AND notion_page_id != ''")
    print(f"Notion pages to update: {len(dirty)}" + (" (dry run — not pushed)" if args.dry_run else ""))
    if args.dry_run:
        return
    ok = fail = 0
    for r in dirty:
        try:
            # Full-row push (properties only on an existing page): status, notes and any listing metadata that
            # dirtied the row earlier all land, so clearing the flag never hides a pending metadata retry.
            if push_opportunity(row_to_opp(r)):
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
