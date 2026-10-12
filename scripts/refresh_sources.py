#!/usr/bin/env python3
"""Re-sync listings we already hold with what their sources report now.

For every enabled (or named) source: re-fetch, update stale metadata on rows we have (deadline,
posted date, link, title), expire rows the source now reports closed / awarded / cancelled, and
retire duplicate postings (same source + solicitation number, or same normalised title + agency),
keeping the row with the latest deadline. Rows with page-chrome titles ("Welcome to …") are expired.
Nothing is scored and no alert is sent.

    python scripts/refresh_sources.py --dry-run                     # report only
    python scripts/refresh_sources.py --sources rhode_island_osp     # apply for one source
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import oppos.config  # noqa: F401
from oppos.scoring.prefilter import _JUNK_TITLE_RE
from oppos.sources.registry import _load_registry, get_enabled_sources
from oppos.storage.db import (_norm_key, _query, expire_if_active, get_excluded_sources, init_db, refresh_opportunity_meta,
                              set_pipeline_status)

ACTIVE = ("new", "qualified", "expiring_soon")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", default="", help="comma-separated source keys (default: enabled sources)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-fetch", action="store_true", help="only dedupe / junk-title pass on stored rows")
    args = ap.parse_args()
    init_db()
    excluded = set(get_excluded_sources())
    wanted = [s.strip() for s in args.sources.split(",") if s.strip()]
    registry = _load_registry()  # key -> (name, fetch)
    sources = get_enabled_sources() if not wanted else [(k, registry[k][0], registry[k][1]) for k in wanted if k in registry]
    verb = "Would" if args.dry_run else "Did"
    refreshed = expired = 0
    if not args.no_fetch:
        for key, name, fetch in sources:
            if key in excluded:
                continue
            try:
                opps = fetch(**({"posted_from": None} if key == "sam_gov" else {}))
            except Exception as e:
                print(f"{name}: fetch failed — {e}")
                continue
            for o in opps:
                if o.get("active") is False:
                    if args.dry_run:
                        row = _query("SELECT pipeline_status FROM opportunities WHERE source_id = ?", (o["source_id"],))
                        if row and row[0]["pipeline_status"] in ACTIVE:
                            expired += 1
                    elif expire_if_active(o["source_id"], "Auto-expired — source reports the listing is no longer open"):
                        expired += 1
                    continue
                if args.dry_run:
                    row = _query("SELECT response_deadline, url, title FROM opportunities WHERE source_id = ?", (o["source_id"],))
                    if row and any(o.get(f) and str(o.get(f)) != str(row[0].get(f) or "") for f in ("response_deadline", "url", "title")):
                        refreshed += 1
                elif refresh_opportunity_meta(o):
                    refreshed += 1
            print(f"{name}: {len(opps)} listings fetched")
    # duplicates + junk titles among active rows
    rows = _query(f"SELECT source_id, source, title, agency, solicitation_number, response_deadline FROM opportunities WHERE pipeline_status IN ({', '.join('?' for _ in ACTIVE)})", ACTIVE)
    junk = [r for r in rows if _JUNK_TITLE_RE.search((r["title"] or "").strip())]
    # Union-find over two keys: same source + solicitation number, and same source + normalised title + agency.
    live = [r for r in rows if r not in junk]
    parent = {r["source_id"]: r["source_id"] for r in live}
    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    def union(a: str, b: str) -> None:
        parent[find(a)] = find(b)
    by_key: dict[tuple, str] = {}
    for r in live:
        sol = (r.get("solicitation_number") or "").strip().lower()
        title = _norm_key(r["title"] or "")
        keys = [(r["source"], "sol", sol)] if sol else []
        if len(title) >= 12:
            keys.append((r["source"], "title", title, (r.get("agency") or "").strip().lower()))
        for k in keys:
            if k in by_key:
                union(r["source_id"], by_key[k])
            else:
                by_key[k] = r["source_id"]
    groups: dict[str, list] = defaultdict(list)
    for r in live:
        groups[find(r["source_id"])].append(r)
    dups = []
    for members in groups.values():
        if len(members) < 2:
            continue
        members.sort(key=lambda r: (r.get("response_deadline") or "", r["source_id"]), reverse=True)
        dups += [(m, members[0]) for m in members[1:]]
    for r in junk:
        if not args.dry_run:
            set_pipeline_status(r["source_id"], "expired", notes=f"Auto-expired — page chrome scraped as title: {r['title'][:60]!r}")
    for m, keep in dups:
        if not args.dry_run:
            set_pipeline_status(m["source_id"], "skipped", notes=f"Duplicate of {keep['source_id']} ({keep['title'][:60]})")
    print(f"{verb} refresh {refreshed} row(s), expire {expired} row(s) the source reports closed, expire {len(junk)} junk-title row(s), "
          f"mark {len(dups)} duplicate(s) skipped.")
    for r in junk[:5]:
        print("  junk:", r["source"], r["source_id"], (r["title"] or "")[:60])
    for m, keep in dups[:8]:
        print("  dup :", m["source"], m["source_id"], "->", keep["source_id"], (m["title"] or "")[:50])


if __name__ == "__main__":
    main()
