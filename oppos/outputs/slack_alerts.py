"""Slack webhook alerts for high-scoring opportunities."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from oppos.config import SLACK_WEBHOOK_URL

logger = logging.getLogger(__name__)


def _build_message(opp: dict[str, Any]) -> dict:
    s2 = opp.get("stage2") or {}
    if isinstance(s2, str):
        try:
            s2 = json.loads(s2)
        except json.JSONDecodeError:
            s2 = {}

    score = opp.get("fit_score", 0)
    action = s2.get("recommended_action", opp.get("recommended_action", "?"))
    title = opp.get("title", "Untitled")
    agency = opp.get("agency", "Unknown")
    deadline = opp.get("response_deadline", "TBD")
    url = opp.get("url", "")
    summary = s2.get("summary", "")
    pattern = s2.get("pattern_match", "")
    similar = s2.get("similar_win", "")
    strengths = s2.get("strengths", [])
    risks = s2.get("risks", [])
    deployment = s2.get("deployment_recommendation", "")

    score_emoji = "🟢" if score >= 70 else "🟡" if score >= 50 else "🔴"

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"{score_emoji} New RFP: {score}/100 — {action.upper()}"},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*<{url}|{title}>*\n"
                    f"*Agency:* {agency}\n"
                    f"*Deadline:* {deadline}\n"
                    f"*Pattern:* {pattern}\n"
                    f"*Similar Win:* {similar or 'None'}\n"
                    f"*Deployment:* {deployment}"
                ),
            },
        },
    ]

    if summary:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Summary:* {summary}"},
        })

    if strengths:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Strengths:* {', '.join(strengths[:5])}"},
        })

    if risks:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Risks:* {', '.join(risks[:3])}"},
        })

    return {"blocks": blocks}


def send_alert(opp: dict[str, Any]) -> bool:
    if not SLACK_WEBHOOK_URL:
        logger.warning("SLACK_WEBHOOK_URL not set — skipping alert")
        return False

    payload = _build_message(opp)

    try:
        resp = httpx.post(SLACK_WEBHOOK_URL, json=payload, timeout=10.0)
        resp.raise_for_status()
        logger.info("Slack alert sent for '%s'", opp.get("title", "?"))
        return True
    except httpx.HTTPError as e:
        logger.error("Slack alert failed: %s", e)
        return False
