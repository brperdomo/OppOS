"""Slack webhook alerts for high-scoring opportunities."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from oppos.config import SLACK_WEBHOOK_URL, SOURCE_STATE_MAP

logger = logging.getLogger(__name__)


def _get_state(opp: dict[str, Any]) -> str:
    """Derive state/region from source key, place_of_performance, or office."""
    state = SOURCE_STATE_MAP.get(opp.get("source", ""), "")
    if not state:
        state = opp.get("place_of_performance") or opp.get("office") or ""
    return state


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

    state = _get_state(opp)

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
                    + (f"*State:* {state}\n" if state else "")
                    + f"*Deadline:* {deadline}\n"
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


def build_sdr_message(opp: dict[str, Any]) -> str:
    """Build a copy-paste ready message for SDRs to create a Salesforce opportunity."""
    agency = opp.get("agency") or "Unknown Agency"
    state = _get_state(opp)
    contact_name = opp.get("contact_name") or ""
    contact_email = opp.get("contact_email") or ""
    title = opp.get("title") or ""
    sol_number = opp.get("solicitation_number") or ""
    deadline = opp.get("response_deadline") or "TBD"
    url = opp.get("url") or ""

    # Combine state + agency: "State of Nevada - Department of Health"
    if state and state != "Federal":
        agency_full = f"State of {state} - {agency}"
    elif state == "Federal":
        agency_full = f"{agency} (Federal)"
    else:
        agency_full = agency

    # Build contact line
    if contact_name and contact_email:
        contact_line = f"Contact is {contact_name} ({contact_email})"
    elif contact_name:
        contact_line = f"Contact is {contact_name}"
    elif contact_email:
        contact_line = f"Contact is {contact_email}"
    else:
        contact_line = "Contact TBD (see RFP for details)"

    # Build reference line with sol number and deadline
    ref_parts = []
    if sol_number:
        ref_parts.append(f"Solicitation: {sol_number}")
    if deadline and deadline != "TBD":
        ref_parts.append(f"Deadline: {deadline}")
    ref_line = " | ".join(ref_parts) if ref_parts else ""

    msg = (
        f"Hi team... may I have an opp created for the following: "
        f"{agency_full}. {contact_line} "
        f"LOB is Workflow (please make Richard opportunity owner).\n\n"
        f"No Hiver at the moment, this is an open RFP sourced through an outbound effort."
    )

    if title:
        msg += f"\n\nRFP: {title}"
    if ref_line:
        msg += f"\n{ref_line}"
    if url:
        msg += f"\n{url}"

    return msg


def _build_pursue_message(opp: dict[str, Any], reason: str = "", notion_url: str = "") -> dict:
    """Build Slack blocks for a 'Pursuing' notification."""
    s2 = opp.get("stage2") or opp.get("stage2_json") or {}
    if isinstance(s2, str):
        try:
            s2 = json.loads(s2)
        except json.JSONDecodeError:
            s2 = {}

    score = opp.get("fit_score", 0)
    title = opp.get("title", "Untitled")
    agency = opp.get("agency", "Unknown")
    state = _get_state(opp)
    deadline = opp.get("response_deadline", "TBD")
    url = opp.get("url", "")
    contact_name = opp.get("contact_name") or ""
    contact_email = opp.get("contact_email") or ""
    sol_number = opp.get("solicitation_number") or ""

    contact_str = ""
    if contact_name and contact_email:
        contact_str = f"{contact_name} ({contact_email})"
    elif contact_name:
        contact_str = contact_name
    elif contact_email:
        contact_str = contact_email

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"🎯 Pursuing: {title[:140]}"},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*Agency:* {agency}\n"
                    + (f"*State:* {state}\n" if state else "")
                    + f"*Fit Score:* {score}/100\n"
                    f"*Deadline:* {deadline}\n"
                    + (f"*Solicitation:* {sol_number}\n" if sol_number else "")
                    + (f"*Contact:* {contact_str}\n" if contact_str else "")
                    + (f"*RFP:* <{url}|View Listing>" if url else "")
                ),
            },
        },
    ]

    if reason:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Pursue Reason:* {reason}"},
        })

    # Add the SDR message as a ready-to-copy block
    sdr_msg = build_sdr_message(opp)
    blocks.append({"type": "divider"})
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"*📋 Salesforce Opp Request (copy/paste):*\n```{sdr_msg}```",
        },
    })

    # Notion link for response drafting
    if notion_url:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*📝 Draft Response:* <{notion_url}|Open in Notion>",
            },
        })

    summary = s2.get("summary", "")
    if summary:
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"_{summary[:300]}_"}],
        })

    return {"blocks": blocks}


def send_pursue_alert(opp: dict[str, Any], reason: str = "", notion_url: str = "") -> bool:
    """Send a Slack notification when an RFP is moved to 'Pursuing'."""
    if not SLACK_WEBHOOK_URL:
        logger.warning("SLACK_WEBHOOK_URL not set — skipping pursue alert")
        return False

    payload = _build_pursue_message(opp, reason, notion_url=notion_url)

    try:
        resp = httpx.post(SLACK_WEBHOOK_URL, json=payload, timeout=10.0)
        resp.raise_for_status()
        logger.info("Pursue alert sent for '%s'", opp.get("title", "?"))
        return True
    except httpx.HTTPError as e:
        logger.error("Pursue alert failed: %s", e)
        return False


def _build_abandon_message(opp: dict[str, Any], reason: str = "", label: str = "Abandoned") -> dict:
    """Build Slack blocks for an 'Abandoned' or 'Skipped' notification."""
    title = opp.get("title", "Untitled")
    agency = opp.get("agency", "Unknown")
    state = _get_state(opp)
    score = opp.get("fit_score", 0)

    header_text = f"🚫 {label}: {title[:140]}"
    detail_parts = f"*Agency:* {agency}\n"
    if state:
        detail_parts += f"*State:* {state}\n"
    detail_parts += f"*Fit Score:* {score}/100"

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": header_text},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": detail_parts},
        },
    ]

    if reason:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Reason:* {reason}"},
        })

    return {"blocks": blocks}


def send_abandon_alert(opp: dict[str, Any], reason: str = "", label: str = "Abandoned") -> bool:
    """Send a Slack notification when an RFP is abandoned or skipped."""
    if not SLACK_WEBHOOK_URL:
        logger.warning("SLACK_WEBHOOK_URL not set — skipping abandon alert")
        return False

    payload = _build_abandon_message(opp, reason, label=label)

    try:
        resp = httpx.post(SLACK_WEBHOOK_URL, json=payload, timeout=10.0)
        resp.raise_for_status()
        logger.info("Abandon alert sent for '%s'", opp.get("title", "?"))
        return True
    except httpx.HTTPError as e:
        logger.error("Abandon alert failed: %s", e)
        return False
