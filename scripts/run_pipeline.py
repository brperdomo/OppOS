#!/usr/bin/env python3
"""OppOS pipeline runner — used by the scheduled GitHub Action and for manual runs.

Fetches opportunities from all enabled sources, routes and scores them through
the two-stage AI qualifier, stores results, syncs to Notion, and sends Slack alerts.

Usage:
    python scripts/run_pipeline.py                          # all enabled sources
    python scripts/run_pipeline.py --days 7                 # last 7 days (SAM.gov)
    python scripts/run_pipeline.py --dry-run                # score but skip Notion/Slack
    python scripts/run_pipeline.py --sources sam_gov        # specific source only
    python scripts/run_pipeline.py --sources sam_gov,nevada_epro
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oppos.config import SLACK_ALERT_MIN_SCORE
from oppos.outputs.notion_sync import push_opportunity
from oppos.outputs.slack_alerts import send_alert
from oppos.pipeline import resolve_sources, run_scan
from oppos.scoring.qualifier import USAGE
from oppos.sources.attachments import download_attachments
from oppos.sources.registry import list_available
from oppos.storage.db import get_unnotified, set_notion_page_id, set_slack_notified

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("oppos.pipeline.cli")


def run(days: int = 30, dry_run: bool = False, source_override: list[str] | None = None) -> dict:
    notion_synced = 0

    def _push(opp: dict) -> None:
        nonlocal notion_synced
        if dry_run:
            logger.info("[DRY RUN] [%s/%s] %s — score=%d action=%s",
                        opp.get("source", "?"), opp.get("lob", "?"), opp.get("title", "?")[:80],
                        opp.get("fit_score", 0), opp.get("recommended_action", "?"))
            return
        attachments = download_attachments(opp)
        page_id = push_opportunity(opp, attachment_paths=attachments)
        if page_id:
            set_notion_page_id(opp["source_id"], page_id)
            notion_synced += 1

    def _progress(idx: int, total: int, name: str) -> None:
        logger.info("[%d/%d] Fetching from %s…", idx + 1, total, name)

    stats = run_scan(
        sources=resolve_sources(source_override),
        days=days,
        on_progress=_progress,
        on_scored=_push,
    )
    stats["notion_synced"] = notion_synced
    stats["slack_alerted"] = 0

    if not dry_run:
        for row in get_unnotified(min_score=SLACK_ALERT_MIN_SCORE):
            if send_alert(row):
                set_slack_notified(row["source_id"])
                stats["slack_alerted"] += 1

    for key, ps in stats["per_source"].items():
        status = "FAIL" if ps["error"] else "ok"
        logger.info("  %-32s %-4s listings=%-4d new=%-4d scored=%-3d %5.1fs %s",
                    key, status, ps["count"], ps["new"], ps["scored"], ps["duration_s"], ps["error"] or "")
    logger.info("Token usage: %s", USAGE)
    logger.info("Pipeline complete: %s", {k: v for k, v in stats.items() if k != "per_source"})
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="OppOS pipeline runner")
    parser.add_argument("--days", type=int, default=30, help="Look back N days for SAM.gov (default: 30)")
    parser.add_argument("--dry-run", action="store_true", help="Score only — skip Notion and Slack")
    parser.add_argument("--sources", type=str, default=None,
                        help="Comma-separated source keys. Default: ENABLED_SOURCES from the environment")
    parser.add_argument("--list-sources", action="store_true", help="List all available sources and exit")
    args = parser.parse_args()

    if args.list_sources:
        print("Available sources:")
        for key, name in list_available():
            print(f"  {key:32s} {name}")
        return

    override = [s.strip() for s in args.sources.split(",")] if args.sources else None
    stats = run(days=args.days, dry_run=args.dry_run, source_override=override)
    if stats["errors"] and stats["sources"] and len(stats["errors"]) == stats["sources"]:
        sys.exit(1)  # every source failed — make the scheduled job red


if __name__ == "__main__":
    main()
