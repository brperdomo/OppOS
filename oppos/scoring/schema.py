"""Helpers for the shared Stage 2 result schema.

Strengths and risks are lists of ``{"claim": str, "evidence": str}``. Older rows
store plain strings; every helper here accepts both so renderers never branch.
"""

from __future__ import annotations

from typing import Any, Iterable

from oppos.scoring.lobs import lob_label  # re-exported for renderers

__all__ = ["normalize_points", "point_claim", "point_evidence", "points_text", "lob_label"]


def point_claim(point: Any) -> str:
    if isinstance(point, dict):
        return str(point.get("claim") or point.get("text") or "").strip()
    return str(point or "").strip()


def point_evidence(point: Any) -> str:
    if isinstance(point, dict):
        ev = str(point.get("evidence") or "").strip()
        return "" if ev.lower() == "inferred" else ev
    return ""


def normalize_points(items: Any, limit: int = 12) -> list[dict[str, str]]:
    """Coerce model output (strings or dicts, possibly malformed) to the canonical shape."""
    out: list[dict[str, str]] = []
    if not isinstance(items, (list, tuple)):
        return out
    for item in items:
        claim = point_claim(item)
        if not claim:
            continue
        evidence = str(item.get("evidence") or "inferred").strip() if isinstance(item, dict) else "inferred"
        out.append({"claim": claim[:300], "evidence": evidence[:300]})
        if len(out) >= limit:
            break
    return out


def points_text(items: Iterable[Any] | None, limit: int | None = None, sep: str = " · ") -> str:
    """Claims only, joined — for compact one-line displays."""
    claims = [point_claim(p) for p in (items or []) if point_claim(p)]
    if limit is not None:
        claims = claims[:limit]
    return sep.join(claims)
