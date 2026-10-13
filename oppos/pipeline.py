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
from oppos.scoring.prefilter import prefilter, probe_links, check_link, DEFERRED
from oppos.scoring.qualifier import qualify
from oppos.sources.registry import FetchFn, get_enabled_sources
from oppos.storage.db import (
    get_excluded_sources,
    init_db,
    is_seen,
    record_source_health,
    set_meta,
    upsert_opportunity, expire_if_active, find_duplicate, refresh_opportunity_meta,
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
    on_refreshed: ScoredFn | None = None,
    on_expired: ScoredFn | None = None,
) -> dict[str, Any]:
    """Scan every source, score new listings, persist them, and record source health.

    Returns stats: fetched, new, filtered_out, scored, sources, errors[], per_source{}.
    `on_scored` is called for each newly scored opportunity whose fit_score meets
    STAGE2_MIN_SCORE (the CLI uses it to push to Notion); `on_refreshed` for each already-held row whose
    listing metadata (deadline, link, title…) changed, so outputs such as Notion can be updated too; `on_expired`
    for each held row the source now reports closed (so its Notion status can follow the database).
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
            # Closed listings first: a re-issued bid (new id) must not be folded into the retired original it replaces.
            inactive_ids = {o["source_id"] for o in opps if o.get("active") is False}
            # Probe the links of listings we have not stored yet — concurrently, cached, bounded — so the prefilter
            # can reject dead links without a serial network wait per listing.
            try:
                probe_links([o.get("url") or "" for o in opps if o.get("active") is not False and not is_seen(o["source_id"])])
            except Exception as e:
                logger.warning("%s: link probing skipped: %s", name, e)
            for opp in sorted(opps, key=lambda o: o.get("active") is not False):
                if opp.get("active") is False:
                    # The source now reports this listing closed / awarded / cancelled: retire our copy if we hold one.
                    if expire_if_active(opp["source_id"], "Auto-expired — source reports the listing is no longer open"):
                        stats["expired_by_source"] = stats.get("expired_by_source", 0) + 1
                        if on_expired:
                            try:
                                on_expired(opp)
                            except Exception as e:
                                logger.error("on_expired failed for %s: %s", opp.get("source_id"), e)
                    continue
                if is_seen(opp["source_id"]):
                    if refresh_opportunity_meta(opp):  # corrected deadline / link / title from the latest fetch
                        stats["refreshed"] = stats.get("refreshed", 0) + 1
                        if on_refreshed:
                            try:
                                on_refreshed(opp)
                            except Exception as e:
                                logger.error("on_refreshed failed for %s: %s", opp.get("source_id"), e)
                    continue
                if check_link(opp.get("url") or "") == DEFERRED:
                    stats["deferred"] = stats.get("deferred", 0) + 1  # link not probed yet (per-source cap): next run
                    continue
                dup = find_duplicate(opp)
                if dup and dup["source_id"] in inactive_ids:
                    dup = None  # the row we hold is the retired original; this is its replacement, store it
                if dup:
                    # Same posting under a new id (addendum / re-issue): keep one row, carry the newer metadata.
                    if refresh_opportunity_meta({**opp, "source_id": dup["source_id"]}) and on_refreshed:
                        try:
                            on_refreshed({**opp, "source_id": dup["source_id"]})
                        except Exception as e:
                            logger.error("on_refreshed failed for %s: %s", dup.get("source_id"), e)
                    stats["duplicates"] = stats.get("duplicates", 0) + 1
                    logger.info("Duplicate of %s skipped: %s", dup["source_id"], opp["source_id"])
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

    excluded = set(get_excluded_sources())
    pending = [o for o in get_unnotified(min_score=min_score)
               if (o.get("pipeline_status") or "new") in _DIGEST_ACTIVE_STATUSES
               and o.get("source") not in excluded]
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
