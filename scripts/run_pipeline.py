#!/usr/bin/env python3
"""OppOS pipeline runner.

Fetches opportunities from all enabled sources, scores them through the
two-stage AI qualifier, stores results, syncs to Notion, and sends Slack alerts.

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
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oppos.config import SLACK_ALERT_MIN_SCORE, STAGE2_MIN_SCORE
from oppos.outputs.notion_sync import push_opportunity
from oppos.outputs.slack_alerts import send_alert
from oppos.scoring.prefilter import prefilter
from oppos.scoring.qualifier import qualify
from oppos.sources.attachments import download_attachments
from oppos.sources.registry import get_enabled_sources, list_available
from oppos.storage.db import (
    get_unnotified,
    init_db,
    is_seen,
    set_notion_page_id,
    set_slack_notified,
    upsert_opportunity,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("oppos.pipeline")


def _fetch_all_sources(days: int, source_override: list[str] | None = None) -> list[dict]:
    from oppos.sources.registry import _load_registry

    if source_override:
        registry = _load_registry()
        sources = [
            (k, registry[k][0], registry[k][1])
            for k in source_override
            if k in registry
        ]
    else:
        sources = get_enabled_sources()

    all_opportunities: list[dict] = []
    posted_from = datetime.now() - timedelta(days=days)

    for key, name, fetch_fn in sources:
        logger.info("Fetching from %s…", name)
        try:
            if key == "sam_gov":
                opps = fetch_fn(posted_from=posted_from)
            else:
                opps = fetch_fn()
            logger.info("%s: %d opportunities", name, len(opps))
            all_opportunities.extend(opps)
        except Exception as e:
            logger.error("%s fetch failed: %s", name, e)

    return all_opportunities


def run(
    days: int = 30,
    dry_run: bool = False,
    source_override: list[str] | None = None,
) -> dict[str, int]:
    stats = {
        "fetched": 0,
        "new": 0,
        "prefilter_rejected": 0,
        "relevant_stage1": 0,
        "scored": 0,
        "notion_synced": 0,
        "slack_alerted": 0,
    }

    init_db()

    opportunities = _fetch_all_sources(days, source_override)
    stats["fetched"] = len(opportunities)
    logger.info("Fetched %d total opportunities across all sources", len(opportunities))

    for opp in opportunities:
        sid = opp["source_id"]
        if is_seen(sid):
            continue
        stats["new"] += 1

        # Rules-based pre-filter — reject obvious non-software (free, instant)
        prefilter(opp)
        if not opp["prefilter"]["passed"]:
            stats["prefilter_rejected"] += 1
            logger.info(
                "Pre-filtered out: '%s' — %s",
                opp.get("title", "?")[:80],
                opp["prefilter"]["reason"],
            )
            continue

        scored = qualify(opp)

        if scored.get("stage1", {}).get("relevant", False) or scored.get("fit_score", 0) > 0:
            stats["relevant_stage1"] += 1

        if scored.get("fit_score", 0) >= STAGE2_MIN_SCORE:
            stats["scored"] += 1

        upsert_opportunity(scored)

        if dry_run:
            logger.info(
                "[DRY RUN] [%s] %s — score=%d action=%s",
                scored.get("source", "?"),
                scored.get("title", "?")[:80],
                scored.get("fit_score", 0),
                scored.get("recommended_action", "?"),
            )
            continue

        if scored.get("fit_score", 0) >= STAGE2_MIN_SCORE:
            attachments = download_attachments(scored)
            page_id = push_opportunity(scored, attachment_paths=attachments)
            if page_id:
                set_notion_page_id(sid, page_id)
                stats["notion_synced"] += 1

    if not dry_run:
        unnotified = get_unnotified(min_score=SLACK_ALERT_MIN_SCORE)
        for row in unnotified:
            if send_alert(row):
                set_slack_notified(row["source_id"])
                stats["slack_alerted"] += 1

    logger.info("Pipeline complete: %s", stats)
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="OppOS pipeline runner")
    parser.add_argument("--days", type=int, default=30, help="Look back N days for SAM.gov (default: 30)")
    parser.add_argument("--dry-run", action="store_true", help="Score only — skip Notion and Slack")
    parser.add_argument(
        "--sources",
        type=str,
        default=None,
        help="Comma-separated source keys (e.g., sam_gov,nevada_epro). Default: use ENABLED_SOURCES from .env",
    )
    parser.add_argument("--list-sources", action="store_true", help="List all available sources and exit")
    args = parser.parse_args()

    if args.list_sources:
        print("Available sources:")
        for key, name in list_available():
            print(f"  {key:20s} {name}")
        return

    source_override = [s.strip() for s in args.sources.split(",")] if args.sources else None
    run(days=args.days, dry_run=args.dry_run, source_override=source_override)


if __name__ == "__main__":
    main()
