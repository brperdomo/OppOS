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
