"""Line-of-business definition used by the router (Stage 1) and scorer (Stage 2)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

PROFILES_DIR = Path(__file__).resolve().parent / "profiles"
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)


def load_profile(key: str) -> tuple[str, dict[str, Any]] | None:
    """Read profiles/<key>.md → (body, frontmatter). None when the file is missing.

    Frontmatter is a small YAML subset: `k: v` scalars and `- item` lists.
    """
    path = PROFILES_DIR / f"{key}.md"
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    meta: dict[str, Any] = {}
    m = _FRONTMATTER_RE.match(text)
    if m:
        current_list: str | None = None
        for raw in m.group(1).splitlines():
            line = raw.rstrip()
            if not line.strip():
                continue
            if line.lstrip().startswith("- ") and current_list:
                meta.setdefault(current_list, []).append(line.lstrip()[2:].strip())
                continue
            if ":" in line and not line.startswith(" "):
                k, _, v = line.partition(":")
                k, v = k.strip(), v.strip()
                if v == "":
                    current_list = k
                    meta.setdefault(k, [])
                else:
                    current_list = None
                    meta[k] = v
        text = text[m.end():]
    return text.strip() + "\n", meta


@dataclass(frozen=True)
class LOB:
    key: str
    label: str
    # One paragraph: what the LOB sells and who buys it. Used by the Stage 1 router.
    router_blurb: str
    # Full positioning profile injected into the Stage 2 system prompt.
    profile: str
    # "full" = vetted positioning profile; "thin" = description only — scores are capped
    # and recommended_action is limited to investigate/skip until a real profile exists.
    depth: str = "thin"
    # Extra JSON schema lines appended to the shared Stage 2 schema (each ends with a comma).
    extras_schema: tuple[str, ...] = ()
    # Defaults for those extras so downstream renderers can rely on the keys.
    extras_defaults: dict = field(default_factory=dict)
    thin_score_cap: int = 59


def make_lob(
    key: str,
    label: str,
    router_blurb: str,
    thin_profile: str,
    extras_schema: tuple[str, ...] = (),
    extras_defaults: dict | None = None,
) -> LOB:
    """Build a LOB from profiles/<key>.md when it exists (depth from its frontmatter,
    default "full"), otherwise from the inline thin description."""
    loaded = load_profile(key)
    if loaded:
        profile, meta = loaded
        depth = str(meta.get("depth", "full")).lower()
        if depth not in ("full", "thin"):
            depth = "full"
    else:
        profile, depth = thin_profile, "thin"
    return LOB(
        key=key, label=label, router_blurb=router_blurb, profile=profile, depth=depth,
        extras_schema=extras_schema, extras_defaults=dict(extras_defaults or {}),
    )
