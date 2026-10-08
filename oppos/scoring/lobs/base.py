"""Line-of-business definition used by the router (Stage 1) and scorer (Stage 2)."""

from __future__ import annotations

from dataclasses import dataclass, field


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
