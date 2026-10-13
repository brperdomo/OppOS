"""One Slack message for every pursuit stage change.

Every change an SDR makes — grab, pursue, submit, win, lose, abandon, put back, draft ready — posts the same
shape: who did what to which RFP, where it stands, and links to act on it. Works in both Slack modes:

* webhook mode (``SLACK_WEBHOOK_URL`` only): one message per change to the webhook's channel;
* bot mode (``SLACK_BOT_TOKEN`` + ``SLACK_DIGEST_CHANNEL``): the same message in the digest channel and, when
  the pursuit has its own ``#rfp-…`` channel, there too.

Plain webhooks can only post, so the buttons are links (My desk, Notion, listing); in-Slack actions such as
"abandon" need an interactivity endpoint Streamlit cannot host.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from oppos.outputs import slack_pursuits as sp

logger = logging.getLogger(__name__)

APP_URL = sp._env("OPPOS_APP_URL").rstrip("/")  # the dashboard, for the "Open on my desk" button

STAGES: dict[str, tuple[str, str]] = {
    "claimed":   ("👋", "Grabbed"),
    "pursuing":  ("🎯", "Pursuing"),
    "draft":     ("✍️", "Draft ready"),
    "submitted": ("📨", "Submitted"),
    "won":       ("🏆", "Won"),
    "lost":      ("📉", "Lost"),
    "abandoned": ("🚫", "Abandoned"),
    "skipped":   ("⏭️", "Skipped"),
    "released":  ("↩️", "Put back"),
}
_CLOSES_CHANNEL = {"won", "lost", "abandoned"}
_NO_PURSUIT_CHANNEL = {"claimed", "released", "skipped"}  # before a channel exists / after the owner let go


def _days_until(raw: str | None) -> int | None:
    if not raw:
        return None
    try:
        return (date.fromisoformat(str(raw)[:10]) - date.today()).days
    except ValueError:
        return None


def _state(opp: dict[str, Any]) -> str:
    from oppos.outputs.slack_alerts import _get_state
    try:
        return _get_state(opp) or ""
    except Exception:
        return ""


def build_status_message(stage: str, opp: dict[str, Any], who: str, reason: str = "",
                         pursuit: dict[str, Any] | None = None, notion_url: str = "",
                         extra: str = "") -> dict[str, Any]:
    """Slack payload (text + blocks) for one stage change. `extra` is a stage-specific line (draft stats…)."""
    emoji, verb = STAGES[stage]
    pursuit = pursuit or {}
    title = (opp.get("title") or "Untitled")[:140]
    agency = opp.get("agency") or ""
    state = _state(opp)
    url = opp.get("url") or ""
    deadline = (pursuit.get("submission_deadline") or opp.get("response_deadline") or "")[:10]
    days = _days_until(deadline)
    try:
        score = int(float(opp.get("fit_score") or 0))
    except (TypeError, ValueError):
        score = 0
    lob = ""
    if opp.get("lob") or pursuit.get("lob"):
        try:
            from oppos.scoring.lobs import lob_label
            lob = lob_label(pursuit.get("lob") or opp.get("lob")) or ""
        except Exception:
            lob = str(pursuit.get("lob") or opp.get("lob"))

    head = f"{emoji} *{verb}* · " + (f"<{url}|{title}>" if url else f"*{title}*")
    where = " · ".join(b for b in (state, agency) if b)
    if where:
        head += f"\n{where}"
    facts = [who or "someone"]
    if deadline:
        facts.append(f"due {deadline}" + (f" ({days}d)" if days is not None and days >= 0 else " (overdue)" if days is not None else ""))
    if lob:
        facts.append(lob)
    if score:
        facts.append(f"fit {score}/100")
    facts.append(datetime.now().strftime("%b %-d, %-I:%M %p"))

    blocks: list[dict[str, Any]] = [
        {"type": "section", "text": {"type": "mrkdwn", "text": head}},
        {"type": "context", "elements": [{"type": "mrkdwn", "text": " · ".join(facts)}]},
    ]
    if reason:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"_{reason[:600]}_"}})
    if extra:
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": extra[:600]}]})
    buttons = []
    if APP_URL:
        sid = opp.get("source_id") or ""
        buttons.append({"type": "button", "text": {"type": "plain_text", "text": "Open on my desk"},
                        "url": f"{APP_URL}/desk" + (f"?open={sid}" if sid else "")})  # deep link to this pursuit
    if notion_url or pursuit.get("notion_page_id") or opp.get("notion_page_id"):
        n = notion_url or f"https://notion.so/{str(pursuit.get('notion_page_id') or opp.get('notion_page_id')).replace('-', '')}"
        buttons.append({"type": "button", "text": {"type": "plain_text", "text": "Notion"}, "url": n})
    if url:
        buttons.append({"type": "button", "text": {"type": "plain_text", "text": "Listing"}, "url": url})
    if buttons:
        blocks.append({"type": "actions", "elements": buttons})

    text = f"{emoji} {verb}: {title}" + (f" — {who}" if who else "") + (f" — {reason[:200]}" if reason else "")
    return {"text": text, "blocks": blocks}


def notify_status(stage: str, opp: dict[str, Any], user: dict[str, Any] | None, reason: str = "",
                  pursuit: dict[str, Any] | None = None, notion_url: str = "", extra: str = "") -> bool:
    """Post the stage message everywhere it belongs. Never raises — Slack must not block the workflow."""
    who = ""
    if user:
        who = user.get("name") or user.get("email") or ""
    payload = build_status_message(stage, opp, who, reason=reason, pursuit=pursuit, notion_url=notion_url, extra=extra)
    sent = False
    try:
        if sp.bot_enabled():
            channel_id = (pursuit or {}).get("slack_channel_id")
            if channel_id and stage not in _NO_PURSUIT_CHANNEL:
                if stage in _CLOSES_CHANNEL:
                    sp.close_pursuit_channel(channel_id, payload["text"])
                else:
                    sp.post(channel_id, payload["text"], payload["blocks"])
                sent = True
            if sp.SLACK_DIGEST_CHANNEL:
                sent = sp.post(sp.SLACK_DIGEST_CHANNEL, payload["text"], payload["blocks"]) is not None or sent
            return sent
        return sp._webhook(payload)
    except Exception as e:
        logger.warning("Slack %s notice failed for %s: %s", stage, opp.get("source_id"), e)
        return False
