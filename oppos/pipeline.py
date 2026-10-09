"""Shared scan loop used by the dashboard button, the CLI, and the scheduled job.

Fetch → prefilter → qualify → store, recording per-source health as it goes so
the dashboard can show which sources are broken, stale, or silent.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from typing import Any, Callable

from oppos.config import STAGE2_MIN_SCORE
from oppos.scoring.prefilter import prefilter
from oppos.scoring.qualifier import qualify
from oppos.sources.registry import FetchFn, get_enabled_sources
from oppos.storage.db import (
    get_excluded_sources,
    init_db,
    is_seen,
    record_source_health,
    set_meta,
    upsert_opportunity,
)

logger = logging.getLogger("oppos.pipeline")

ProgressFn = Callable[[int, int, str], None]
ScoredFn = Callable[[dict[str, Any]], None]
Source = tuple[str, str, FetchFn]


def resolve_sources(keys: list[str] | None) -> list[Source]:
    """Explicit keys → registry entries; None → ENABLED_SOURCES."""
    if not keys:
        return get_enabled_sources()
    from oppos.sources.registry import _load_registry

    registry = _load_registry()
    sources: list[Source] = []
    for k in keys:
        if k in registry:
            name, fn = registry[k]
            sources.append((k, name, fn))
        else:
            logger.warning("Unknown source '%s' — skipping", k)
    return sources


def run_scan(
    sources: list[Source] | None = None,
    days: int = 14,
    on_progress: ProgressFn | None = None,
    on_scored: ScoredFn | None = None,
) -> dict[str, Any]:
    """Scan every source, score new listings, persist them, and record source health.

    Returns stats: fetched, new, filtered_out, scored, sources, errors[], per_source{}.
    `on_scored` is called for each newly scored opportunity whose fit_score meets
    STAGE2_MIN_SCORE (the CLI uses it to push to Notion).
    """
    init_db()
    sources = sources if sources is not None else get_enabled_sources()
    excluded = set(get_excluded_sources())
    if excluded:
        skipped = [name for key, name, _ in sources if key in excluded]
        sources = [s for s in sources if s[0] not in excluded]
        if skipped:
            logger.info("Skipping excluded sources: %s", ", ".join(skipped))
    total = len(sources)
    posted_from = datetime.now() - timedelta(days=days)

    stats: dict[str, Any] = {
        "fetched": 0, "new": 0, "filtered_out": 0, "scored": 0,
        "sources": total, "errors": [], "per_source": {},
    }

    for idx, (key, name, fetch_fn) in enumerate(sources):
        if on_progress:
            on_progress(idx, total, name)

        t0 = time.monotonic()
        error: str | None = None
        count = new = scored = 0
        try:
            opps = fetch_fn(posted_from=posted_from) if key == "sam_gov" else fetch_fn()
            count = len(opps)
            stats["fetched"] += count
            for opp in opps:
                if is_seen(opp["source_id"]):
                    continue
                new += 1
                stats["new"] += 1
                prefilter(opp)
                if not opp["prefilter"]["passed"]:
                    stats["filtered_out"] += 1
                    continue
                qualified = qualify(opp)
                upsert_opportunity(qualified)
                if qualified.get("fit_score", 0) >= STAGE2_MIN_SCORE:
                    scored += 1
                    stats["scored"] += 1
                    if on_scored:
                        try:
                            on_scored(qualified)
                        except Exception as e:  # downstream failures must not abort the scan
                            logger.error("on_scored failed for %s: %s", qualified.get("source_id"), e)
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
            stats["errors"].append(f"{name}: {error}")
            logger.error("%s fetch failed: %s", name, error)

        duration = time.monotonic() - t0
        stats["per_source"][key] = {"name": name, "count": count, "new": new, "scored": scored,
                                    "error": error, "duration_s": round(duration, 1)}
        try:
            record_source_health(key, name, ok=error is None, count=count, new=new,
                                 error=error, duration_s=duration)
        except Exception as e:
            logger.warning("Could not record source health for %s: %s", key, e)

    set_meta("last_scan", datetime.utcnow().isoformat())
    logger.info("Scan complete: %s", {k: v for k, v in stats.items() if k != "per_source"})
    return stats


# ---------------------------------------------------------------------------
# Slack notification after a scan
# ---------------------------------------------------------------------------

_DIGEST_ACTIVE_STATUSES = ("new", "qualified", "expiring_soon")
DIGEST_MAX_ITEMS = 25


def notify_after_scan(stats: dict[str, Any], min_score: int) -> int:
    """Send Slack notifications for every stored, still-unnotified opportunity.

    Digest mode: one message listing pending high-fit rows (persisted, so a
    failed send is retried on the next scan) plus the in-flight board.
    Individual mode: one webhook alert per row. Returns rows marked notified.
    """
    from oppos.outputs import slack_pursuits as sp
    from oppos.outputs.slack_alerts import send_alert
    from oppos.pursuits import OPEN_STAGES, board_rows
    from oppos.storage.db import get_opps_by_ids, get_unnotified, list_pursuits, set_slack_notified

    pending = [o for o in get_unnotified(min_score=min_score)
               if (o.get("pipeline_status") or "new") in _DIGEST_ACTIVE_STATUSES]
    notified = 0

    if sp.SLACK_ALERT_MODE == "digest":
        batch = pending[:DIGEST_MAX_ITEMS]
        open_pursuits = list_pursuits(status=OPEN_STAGES)
        in_flight = board_rows(open_pursuits, get_opps_by_ids([p["source_id"] for p in open_pursuits]))
        if not batch and not in_flight:
            return 0
        if sp.send_digest(batch, stats.get("sources", 0), stats.get("fetched", 0), in_flight):
            for o in batch:
                set_slack_notified(o["source_id"])
            notified = len(batch)
        else:
            logger.warning("Digest send failed — %d opportunities stay unnotified for the next run", len(batch))
        return notified

    for row in pending:
        if send_alert(row):
            set_slack_notified(row["source_id"])
            notified += 1
    return notified
