"""Two-stage AI qualification pipeline using Claude.

Stage 1 (router): Haiku — which Nutrient line(s) of business could address this
RFP, if any. Inclusive by design.
Stage 2 (deep score): Sonnet — evidence-backed structured scoring against the
primary LOB's positioning profile. Thin-profile LOBs are capped and limited to
investigate/skip until a vetted profile exists.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import anthropic

from oppos.config import (
    ANTHROPIC_API_KEY,
    SCORING_MODEL_STAGE1,
    SCORING_MODEL_STAGE2,
    STAGE1_FIT_THRESHOLD,
)
from oppos.scoring.lobs import DEFAULT_LOB, LOBS, LOB, get_lob
from oppos.scoring.schema import normalize_points

logger = logging.getLogger(__name__)

_client: anthropic.Anthropic | None = None

# Running token usage for this process — read by eval/cost reporting.
USAGE: dict[str, int] = {"calls": 0, "input_tokens": 0, "output_tokens": 0}

# Router candidates below this confidence are dropped.
ROUTER_MIN_CONFIDENCE = 0.3
# Secondary LOBs at or above this confidence are recorded on the result.
SECONDARY_LOB_MIN_CONFIDENCE = 0.5

_ACTIONS = {"pursue", "investigate", "monitor", "skip"}


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


def _track(resp: Any) -> None:
    usage = getattr(resp, "usage", None)
    USAGE["calls"] += 1
    if usage is not None:
        USAGE["input_tokens"] += int(getattr(usage, "input_tokens", 0) or 0)
        USAGE["output_tokens"] += int(getattr(usage, "output_tokens", 0) or 0)


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

def _router_system() -> str:
    lob_lines = "\n".join(f"- `{l.key}` — {l.label}: {l.router_blurb}" for l in LOBS.values())
    return f"""You are the intake router for Nutrient, a document-software company with these lines of business (LOBs):

{lob_lines}
- `none` — no Nutrient LOB could plausibly address this.

Given an RFP title, description, and metadata, decide which LOBs COULD address it. Be INCLUSIVE — we would rather route a false positive than miss a fit. List every plausible LOB with a confidence (0.0-1.0). Return `none` only for things that are clearly unrelated (construction, staffing, pure hardware, unrelated software categories such as ERP or payroll with no document component).

Also set `component_only: true` when the document-related need is a small line item inside a much larger scope (a full ERP replacement, a construction program with a "document portal" requirement, a systems-integrator bid).

Respond with ONLY valid JSON:
{{"lobs": [{{"lob": "<key>", "confidence": 0.0-1.0, "reason": "<short>"}}], "component_only": true/false, "reason": "<one sentence>"}}"""


STAGE1_SYSTEM = _router_system()

_SHARED_SCORING = """## Scoring Instructions

Analyze the RFP against the profile above and produce a structured assessment. Be specific — reference actual capabilities, customer evidence, and deployment options from the profile.

For fit_score (0-100):
- 80-100: Strong fit — matches a proven pattern, clear capability alignment
- 60-79: Good fit — mostly aligned, some gaps or unknowns
- 40-59: Possible fit — partial alignment, needs investigation
- 20-39: Weak fit — significant gaps, low win probability
- 0-19: Poor fit — wrong category entirely

## Evidence rules (strict)
- Every strength and every risk MUST carry `evidence`: a short verbatim quote (25 words or fewer) from the RFP text that supports it. If nothing in the RFP supports it directly, write exactly "inferred" — never paraphrase and present it as a quote.
- Put anything that matters but is not stated in the RFP into `knowledge_gaps` (e.g. "hosting requirements not stated", "incumbent vendor unknown", "user counts not given"). Never fill a gap with a guess.
- Never invent certifications, customers, pricing, or capabilities that are not in the profile above. If the RFP asks for something the profile does not cover, that is a risk, not a strength.
"""


def _stage2_system(lob: LOB) -> str:
    extras = "\n    ".join(lob.extras_schema)
    extras_block = f"    {extras}\n" if extras else ""
    thin = ""
    if lob.depth != "full":
        thin = f"""
## IMPORTANT — thin profile
The {lob.label} profile above is a description, not a vetted positioning profile. Score conservatively: cap fit_score at {lob.thin_score_cap}, use recommended_action "investigate" or "skip" only, and list what a human must verify in knowledge_gaps.
"""
    return f"""You are an expert RFP qualifier for Nutrient {lob.label}. Analyze the opportunity and score how well it fits this line of business.

{lob.profile}
{thin}
{_SHARED_SCORING}
Respond with ONLY valid JSON matching this schema:
{{
    "fit_score": <int 0-100>,
    "fit_tier": <int 1-3>,
    "lob": "{lob.key}",
    "industry": "<primary industry vertical>",
    "strengths": [{{"claim": "<specific capability match>", "evidence": "<verbatim RFP quote or 'inferred'>"}}],
    "risks": [{{"claim": "<specific gap, missing certification, or concern>", "evidence": "<verbatim RFP quote or 'inferred'>"}}],
    "knowledge_gaps": ["<what the RFP does not tell us that matters>"],
{extras_block}    "competitive_notes": "<who we might compete against, any displacement opportunity>",
    "recommended_action": "<pursue | investigate | monitor | skip>",
    "summary": "<2-3 sentence executive summary for the SDR>"
}}"""


_STAGE2_SYSTEM_CACHE: dict[str, str] = {}


def stage2_system_for(lob_key: str) -> str:
    lob = get_lob(lob_key) or LOBS[DEFAULT_LOB]
    if lob.key not in _STAGE2_SYSTEM_CACHE:
        _STAGE2_SYSTEM_CACHE[lob.key] = _stage2_system(lob)
    return _STAGE2_SYSTEM_CACHE[lob.key]


# Backward-compatible alias (Workflow was the only LOB before the router existed).
STAGE2_SYSTEM = stage2_system_for(DEFAULT_LOB)


def _extract_json(text: str) -> str:
    """Strip markdown code fences if present."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    return text


def _repair_and_parse_json(text: str) -> dict:
    """Try to parse JSON, repairing common LLM output issues if needed."""
    raw = _extract_json(text)

    # First try: direct parse
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Repair: replace literal newlines inside string values with \\n
    import re
    repaired = re.sub(
        r'(?<=": ")(.*?)(?="[,\s\n]*["}])',
        lambda m: m.group(0).replace("\n", "\\n").replace("\t", "\\t"),
        raw,
        flags=re.DOTALL,
    )
    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        pass

    # Repair: truncate at last complete key-value pair and close the object
    # Find the last valid "key": value pattern followed by a comma or brace
    last_good = raw.rfind('",')
    if last_good > 0:
        truncated = raw[:last_good + 1] + "}"
        # Balance any unclosed arrays
        open_brackets = truncated.count("[") - truncated.count("]")
        truncated = truncated[:-1] + ("]" * open_brackets) + "}"
        try:
            return json.loads(truncated)
        except json.JSONDecodeError:
            pass

    # Give up — raise so caller hits the fallback
    raise json.JSONDecodeError("Could not repair JSON", raw, 0)


def _build_opportunity_text(opp: dict[str, Any], attachment_text: str = "") -> str:
    parts = [
        f"Title: {opp.get('title', 'N/A')}",
        f"Agency: {opp.get('agency', 'N/A')}",
        f"Notice Type: {opp.get('notice_type', 'N/A')}",
        f"NAICS: {opp.get('naics_code', 'N/A')}",
        f"Set-Aside: {opp.get('set_aside', 'N/A')}",
        f"Classification Code: {opp.get('classification_code', 'N/A')}",
        f"Place of Performance: {opp.get('place_of_performance', 'N/A')}",
        f"Response Deadline: {opp.get('response_deadline', 'N/A')}",
        f"URL: {opp.get('url', 'N/A')}",
    ]
    desc = opp.get("description", "")
    if desc:
        parts.append(f"\nDescription:\n{desc[:8000]}")
    if attachment_text:
        parts.append(f"\n--- RFP ATTACHMENT CONTENT (extracted via OCR) ---\n{attachment_text}")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Stage 1 — LOB router
# ---------------------------------------------------------------------------

def _router_fallback(reason: str) -> dict[str, Any]:
    """On any failure, stay inclusive: route to the default LOB at low confidence."""
    return {
        "relevant": True,
        "confidence": 0.5,
        "reason": reason,
        "lobs": [{"lob": DEFAULT_LOB, "confidence": 0.5, "reason": "fallback"}],
        "component_only": False,
    }


def _normalize_router(raw: dict[str, Any]) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    none_conf: float | None = None
    for item in raw.get("lobs") or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("lob", "")).strip().lower()
        try:
            conf = float(item.get("confidence", 0) or 0)
        except (TypeError, ValueError):
            conf = 0.0
        conf = max(0.0, min(1.0, conf))
        if key == "none":
            none_conf = conf
        elif key in LOBS and conf >= ROUTER_MIN_CONFIDENCE:
            candidates.append({"lob": key, "confidence": round(conf, 2), "reason": str(item.get("reason", ""))[:200]})
    candidates.sort(key=lambda c: -c["confidence"])
    relevant = bool(candidates)
    if relevant:
        confidence = candidates[0]["confidence"]
    else:
        confidence = none_conf if none_conf is not None else 0.8
    return {
        "relevant": relevant,
        "confidence": confidence,
        "reason": str(raw.get("reason", ""))[:300],
        "lobs": candidates,
        "component_only": bool(raw.get("component_only", False)),
    }


def stage1_filter(opportunity: dict[str, Any], attachment_text: str = "") -> dict[str, Any]:
    """Route to LOB(s). Returns {"relevant", "confidence", "reason", "lobs": [...], "component_only"}.

    `relevant` is True when at least one LOB is a plausible candidate; `confidence`
    is the top candidate's confidence (or the confidence in `none` when rejected).
    """
    client = _get_client()
    opp_text = _build_opportunity_text(opportunity, attachment_text)

    try:
        resp = client.messages.create(
            model=SCORING_MODEL_STAGE1,
            max_tokens=400,
            system=STAGE1_SYSTEM,
            messages=[{"role": "user", "content": opp_text}],
        )
        _track(resp)
        raw = _repair_and_parse_json(resp.content[0].text)
        return _normalize_router(raw)
    except (json.JSONDecodeError, IndexError, KeyError, AttributeError) as e:
        logger.warning("Stage 1 parse error for '%s': %s", opportunity.get("title", "?"), e)
        return _router_fallback(f"Parse error — defaulting to {DEFAULT_LOB}: {e}")
    except anthropic.APIError as e:
        logger.error("Stage 1 API error: %s", e)
        return _router_fallback(f"API error — defaulting to {DEFAULT_LOB}: {e}")


# ---------------------------------------------------------------------------
# Stage 2 — per-LOB deep score
# ---------------------------------------------------------------------------

def _tier_for(score: int) -> int:
    return 1 if score >= 80 else 2 if score >= 60 else 3


def _normalize_stage2(result: dict[str, Any], lob: LOB) -> dict[str, Any]:
    out: dict[str, Any] = dict(lob.extras_defaults)
    out.update(result or {})
    out["lob"] = lob.key
    out["strengths"] = normalize_points(out.get("strengths"))
    out["risks"] = normalize_points(out.get("risks"))
    gaps = out.get("knowledge_gaps") or []
    out["knowledge_gaps"] = [str(g).strip()[:200] for g in gaps if str(g).strip()][:10] if isinstance(gaps, list) else []

    try:
        score = int(round(float(out.get("fit_score", 0) or 0)))
    except (TypeError, ValueError):
        score = 0
    score = max(0, min(100, score))

    action = str(out.get("recommended_action", "investigate") or "investigate").strip().lower()
    if action not in _ACTIONS:
        action = "investigate"

    if lob.depth != "full":
        score = min(score, lob.thin_score_cap)
        if action == "pursue":
            action = "investigate"

    out["fit_score"] = score
    out["recommended_action"] = action
    out["profile_depth"] = lob.depth
    out["fit_tier"] = _tier_for(score)  # always from the final score — the thin cap may have lowered it
    out["summary"] = str(out.get("summary", "") or "")
    out["industry"] = str(out.get("industry", "") or "")
    out["competitive_notes"] = str(out.get("competitive_notes", "") or "")
    return out


def _stage2_failure(lob: LOB, message: str) -> dict[str, Any]:
    out: dict[str, Any] = dict(lob.extras_defaults)
    out.update({
        "fit_score": 0,
        "fit_tier": 3,
        "lob": lob.key,
        "industry": "",
        "strengths": [],
        "risks": [{"claim": "Scoring failed — manual review needed", "evidence": "inferred"}],
        "knowledge_gaps": [],
        "competitive_notes": "",
        "recommended_action": "investigate",
        "summary": message,
        "profile_depth": lob.depth,
    })
    return out


def stage2_score(
    opportunity: dict[str, Any],
    attachment_text: str = "",
    lob_key: str | None = None,
) -> dict[str, Any]:
    """Deep qualification scoring against one LOB's profile. Returns the structured assessment."""
    lob = get_lob(lob_key or opportunity.get("lob")) or LOBS[DEFAULT_LOB]
    client = _get_client()
    opp_text = _build_opportunity_text(opportunity, attachment_text)

    try:
        resp = client.messages.create(
            model=SCORING_MODEL_STAGE2,
            max_tokens=1400,
            system=stage2_system_for(lob.key),
            messages=[{"role": "user", "content": f"Score this RFP opportunity:\n\n{opp_text}"}],
        )
        _track(resp)
        result = _repair_and_parse_json(resp.content[0].text)
        return _normalize_stage2(result, lob)
    except (json.JSONDecodeError, IndexError, KeyError, AttributeError) as e:
        logger.warning("Stage 2 parse error for '%s': %s", opportunity.get("title", "?"), e)
        return _stage2_failure(lob, f"Automated scoring failed: {e}")
    except anthropic.APIError as e:
        logger.error("Stage 2 API error: %s", e)
        return _stage2_failure(lob, f"Automated scoring failed: {e}")


def _primary_lob(opportunity: dict[str, Any], lob_key: str | None = None) -> str:
    if lob_key and get_lob(lob_key):
        return get_lob(lob_key).key
    if get_lob(opportunity.get("lob")):
        return get_lob(opportunity.get("lob")).key
    s1 = opportunity.get("stage1") or {}
    if isinstance(s1, dict) and s1.get("lobs"):
        return s1["lobs"][0]["lob"]
    return DEFAULT_LOB


def _attach_stage2(opportunity: dict[str, Any], s2: dict[str, Any]) -> None:
    s1 = opportunity.get("stage1") or {}
    if isinstance(s1, dict):
        secondary = [
            c["lob"] for c in (s1.get("lobs") or [])[1:]
            if c.get("confidence", 0) >= SECONDARY_LOB_MIN_CONFIDENCE and c.get("lob") != s2.get("lob")
        ]
        if secondary:
            s2["secondary_lobs"] = secondary
        if s1.get("component_only"):
            s2["component_only"] = True
    opportunity["stage2"] = s2
    opportunity["lob"] = s2.get("lob", DEFAULT_LOB)
    opportunity["fit_score"] = s2.get("fit_score", 0)
    opportunity["recommended_action"] = s2.get("recommended_action", "investigate")


def force_score(
    opportunity: dict[str, Any],
    attachment_text: str = "",
    lob_key: str | None = None,
) -> dict[str, Any]:
    """Skip Stage 1 and go straight to deep scoring.

    Use when Stage 1 incorrectly filtered out a relevant opportunity, or to
    re-score an opportunity against a specific LOB.
    """
    lob = _primary_lob(opportunity, lob_key)
    s2 = stage2_score(opportunity, attachment_text, lob_key=lob)
    opportunity["stage1"] = {
        "relevant": True,
        "confidence": 1.0,
        "reason": "Force-scored — Stage 1 bypassed",
        "lobs": [{"lob": lob, "confidence": 1.0, "reason": "forced"}],
        "component_only": False,
    }
    _attach_stage2(opportunity, s2)
    logger.info(
        "Force-scored [%s]: '%s' — %d/100 (%s)",
        lob, opportunity.get("title", "?"), opportunity["fit_score"], opportunity["recommended_action"],
    )
    return opportunity


def qualify(opportunity: dict[str, Any], attachment_text: str = "") -> dict[str, Any]:
    """Run the full two-stage pipeline. Returns the opportunity enriched with scoring."""
    s1 = stage1_filter(opportunity, attachment_text)
    opportunity["stage1"] = s1

    if not s1["relevant"] and s1["confidence"] > STAGE1_FIT_THRESHOLD:
        opportunity["stage2"] = None
        opportunity["lob"] = None
        opportunity["fit_score"] = 0
        opportunity["recommended_action"] = "skip"
        logger.info("Filtered out: '%s' — %s", opportunity.get("title", "?"), s1["reason"])
        return opportunity

    primary = s1["lobs"][0]["lob"] if s1["lobs"] else DEFAULT_LOB
    s2 = stage2_score(opportunity, attachment_text, lob_key=primary)
    _attach_stage2(opportunity, s2)

    logger.info(
        "Scored [%s]: '%s' — %d/100 (%s)",
        opportunity["lob"], opportunity.get("title", "?"), opportunity["fit_score"], opportunity["recommended_action"],
    )
    return opportunity
