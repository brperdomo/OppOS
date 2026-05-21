"""Two-stage AI qualification pipeline using Claude.

Stage 1 (fast filter): Haiku — binary relevance check, cheap and fast.
Stage 2 (deep score): Sonnet — structured scoring with pattern matching.
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
from oppos.scoring.capability_profile import CAPABILITY_PROFILE

logger = logging.getLogger(__name__)

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


STAGE1_SYSTEM = """You are a fast RFP relevance filter for Nutrient Workflow, an enterprise process automation platform.

Given an RFP title, description, and metadata, determine if this opportunity COULD be relevant to a workflow automation / case management / document processing platform.

Be INCLUSIVE at this stage — we'd rather have false positives than miss good opportunities. Only reject things that are clearly irrelevant (pure infrastructure, staffing, unrelated software).

Respond with ONLY valid JSON:
{"relevant": true/false, "confidence": 0.0-1.0, "reason": "one sentence"}"""

STAGE2_SYSTEM = f"""You are an expert RFP qualifier for Nutrient Workflow. Your job is to deeply analyze each opportunity and score how well it fits Nutrient Workflow's capabilities.

{CAPABILITY_PROFILE}

## Scoring Instructions

Analyze the RFP against Nutrient Workflow's capabilities and produce a structured assessment. Be specific — reference actual capabilities, customer evidence, and deployment options.

For fit_score (0-100):
- 80-100: Strong fit — matches a proven pattern, clear capability alignment
- 60-79: Good fit — mostly aligned, some gaps or unknowns
- 40-59: Possible fit — partial alignment, needs investigation
- 20-39: Weak fit — significant gaps, low win probability
- 0-19: Poor fit — wrong category entirely

Respond with ONLY valid JSON matching this schema:
{{
    "fit_score": <int 0-100>,
    "fit_tier": <int 1-3>,
    "pattern_match": "<closest pattern: case_management | hr_compliance | guided_decision_support | financial_approvals | it_request_management | ap_invoice | other>",
    "similar_win": "<closest past win or customer example, or null>",
    "industry": "<primary industry vertical>",
    "strengths": ["<specific Workflow capabilities that match>"],
    "risks": ["<specific gaps, missing certifications, or concerns>"],
    "deployment_recommendation": "<standard_cloud | enhanced_cloud | self_managed | private_cluster | tbs_hosting>",
    "competitive_notes": "<who might we compete against, any displacement opportunity>",
    "recommended_action": "<pursue | investigate | monitor | skip>",
    "summary": "<2-3 sentence executive summary for Bryan>"
}}"""


def _extract_json(text: str) -> str:
    """Strip markdown code fences if present."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    return text


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


def stage1_filter(opportunity: dict[str, Any], attachment_text: str = "") -> dict[str, Any]:
    """Fast relevance check. Returns {"relevant": bool, "confidence": float, "reason": str}."""
    client = _get_client()
    opp_text = _build_opportunity_text(opportunity, attachment_text)

    try:
        resp = client.messages.create(
            model=SCORING_MODEL_STAGE1,
            max_tokens=200,
            system=STAGE1_SYSTEM,
            messages=[{"role": "user", "content": opp_text}],
        )
        result = json.loads(_extract_json(resp.content[0].text))
        result.setdefault("relevant", False)
        result.setdefault("confidence", 0.0)
        result.setdefault("reason", "")
        return result
    except (json.JSONDecodeError, IndexError, KeyError) as e:
        logger.warning("Stage 1 parse error for '%s': %s", opportunity.get("title", "?"), e)
        return {"relevant": True, "confidence": 0.5, "reason": "Parse error — defaulting to relevant"}
    except anthropic.APIError as e:
        logger.error("Stage 1 API error: %s", e)
        return {"relevant": True, "confidence": 0.5, "reason": f"API error — defaulting to relevant: {e}"}


def stage2_score(opportunity: dict[str, Any], attachment_text: str = "") -> dict[str, Any]:
    """Deep qualification scoring. Returns full structured assessment."""
    client = _get_client()
    opp_text = _build_opportunity_text(opportunity, attachment_text)

    try:
        resp = client.messages.create(
            model=SCORING_MODEL_STAGE2,
            max_tokens=1000,
            system=STAGE2_SYSTEM,
            messages=[{"role": "user", "content": f"Score this RFP opportunity:\n\n{opp_text}"}],
        )
        result = json.loads(_extract_json(resp.content[0].text))
        return result
    except (json.JSONDecodeError, IndexError, KeyError) as e:
        logger.warning("Stage 2 parse error for '%s': %s", opportunity.get("title", "?"), e)
        return {
            "fit_score": 0,
            "fit_tier": 3,
            "pattern_match": "other",
            "similar_win": None,
            "strengths": [],
            "risks": ["Scoring failed — manual review needed"],
            "recommended_action": "investigate",
            "summary": f"Automated scoring failed: {e}",
        }
    except anthropic.APIError as e:
        logger.error("Stage 2 API error: %s", e)
        return {
            "fit_score": 0,
            "fit_tier": 3,
            "pattern_match": "other",
            "similar_win": None,
            "strengths": [],
            "risks": [f"API error: {e}"],
            "recommended_action": "investigate",
            "summary": f"Automated scoring failed: {e}",
        }


def qualify(opportunity: dict[str, Any], attachment_text: str = "") -> dict[str, Any]:
    """Run the full two-stage pipeline. Returns the opportunity enriched with scoring."""
    s1 = stage1_filter(opportunity, attachment_text)
    opportunity["stage1"] = s1

    if not s1["relevant"] and s1["confidence"] > STAGE1_FIT_THRESHOLD:
        opportunity["stage2"] = None
        opportunity["fit_score"] = 0
        opportunity["recommended_action"] = "skip"
        logger.info("Filtered out: '%s' — %s", opportunity.get("title", "?"), s1["reason"])
        return opportunity

    s2 = stage2_score(opportunity, attachment_text)
    opportunity["stage2"] = s2
    opportunity["fit_score"] = s2.get("fit_score", 0)
    opportunity["recommended_action"] = s2.get("recommended_action", "investigate")

    logger.info(
        "Scored: '%s' — %d/100 (%s)",
        opportunity.get("title", "?"),
        opportunity["fit_score"],
        opportunity["recommended_action"],
    )
    return opportunity
