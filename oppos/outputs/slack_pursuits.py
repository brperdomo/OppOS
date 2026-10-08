"""Slack Web API integration for pursuits (bot token) with webhook fallback.

Requires SLACK_BOT_TOKEN with scopes: chat:write, channels:manage, channels:read,
pins:write, users:read, users:read.email. Without a bot token every function
degrades to the incoming webhook used by slack_alerts (no channels, no invites).
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

import httpx

from oppos.config import SLACK_WEBHOOK_URL

logger = logging.getLogger(__name__)

_API = "https://slack.com/api/"

def _env(name: str, default: str = "") -> str:
    """Env lookup that treats empty strings (e.g. unset GitHub `vars`) as missing."""
    return (os.environ.get(name) or "").strip() or default


SLACK_BOT_TOKEN = _env("SLACK_BOT_TOKEN")
SLACK_DIGEST_CHANNEL = _env("SLACK_DIGEST_CHANNEL")          # channel id or #name
SLACK_PURSUIT_CHANNEL_PREFIX = _env("SLACK_PURSUIT_CHANNEL_PREFIX", "rfp-")
SLACK_ARCHIVE_ON_CLOSE = _env("SLACK_ARCHIVE_ON_CLOSE", "true").lower() in ("1", "true", "yes")
# "digest" = one summary per scan to SLACK_DIGEST_CHANNEL; "individual" = one webhook alert per opp.
SLACK_ALERT_MODE = _env("SLACK_ALERT_MODE", "digest" if (SLACK_BOT_TOKEN and SLACK_DIGEST_CHANNEL) else "individual")
if SLACK_ALERT_MODE not in ("digest", "individual"):
    SLACK_ALERT_MODE = "individual"


class SlackError(RuntimeError):
    pass


def bot_enabled() -> bool:
    return bool(SLACK_BOT_TOKEN)


def _call(method: str, **payload: Any) -> dict[str, Any]:
    if not SLACK_BOT_TOKEN:
        raise SlackError("SLACK_BOT_TOKEN not set")
    resp = httpx.post(
        _API + method,
        headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}", "Content-Type": "application/json; charset=utf-8"},
        json=payload,
        timeout=15.0,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise SlackError(f"{method}: {data.get('error', 'unknown_error')}")
    return data


def _webhook(payload: dict[str, Any]) -> bool:
    if not SLACK_WEBHOOK_URL:
        return False
    try:
        httpx.post(SLACK_WEBHOOK_URL, json=payload, timeout=10.0).raise_for_status()
        return True
    except httpx.HTTPError as e:
        logger.error("Slack webhook failed: %s", e)
        return False


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------

def slugify_channel(text: str, prefix: str = SLACK_PURSUIT_CHANNEL_PREFIX, max_len: int = 80) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return (prefix + slug)[:max_len].rstrip("-") or (prefix + "pursuit")


def lookup_user_id(email: str | None) -> str | None:
    if not email or not bot_enabled():
        return None
    try:
        return _call("users.lookupByEmail", email=email)["user"]["id"]
    except (SlackError, KeyError, httpx.HTTPError) as e:
        logger.info("Slack user lookup failed for %s: %s", email, e)
        return None


def create_channel(name: str) -> tuple[str, str]:
    """Create a public channel; on name collision append -2, -3, …  Returns (id, name)."""
    base = name
    for attempt in range(1, 10):
        candidate = base if attempt == 1 else f"{base[: 80 - len(str(attempt)) - 1]}-{attempt}"
        try:
            ch = _call("conversations.create", name=candidate, is_private=False)["channel"]
            return ch["id"], ch["name"]
        except SlackError as e:
            if "name_taken" in str(e):
                continue
            raise
    raise SlackError("could not find a free channel name")


def invite(channel_id: str, user_ids: list[str]) -> None:
    ids = [u for u in user_ids if u]
    if not ids:
        return
    try:
        _call("conversations.invite", channel=channel_id, users=",".join(ids))
    except SlackError as e:
        if "already_in_channel" not in str(e):
            logger.warning("Slack invite failed: %s", e)


def post(channel: str, text: str, blocks: list[dict] | None = None) -> str | None:
    payload: dict[str, Any] = {"channel": channel, "text": text}
    if blocks:
        payload["blocks"] = blocks
    try:
        return _call("chat.postMessage", **payload).get("ts")
    except SlackError as e:
        logger.error("Slack post failed: %s", e)
        return None


def pin(channel_id: str, ts: str | None) -> None:
    if ts:
        try:
            _call("pins.add", channel=channel_id, timestamp=ts)
        except SlackError as e:
            logger.info("Slack pin failed: %s", e)


def set_topic(channel_id: str, topic: str) -> None:
    try:
        _call("conversations.setTopic", channel=channel_id, topic=topic[:250])
    except SlackError as e:
        logger.info("Slack setTopic failed: %s", e)


def archive(channel_id: str) -> bool:
    try:
        _call("conversations.archive", channel=channel_id)
        return True
    except SlackError as e:
        logger.info("Slack archive failed: %s", e)
        return False


def channel_url(channel_id: str | None) -> str:
    return f"https://slack.com/app_redirect?channel={channel_id}" if channel_id else ""


# ---------------------------------------------------------------------------
# Pursuit lifecycle
# ---------------------------------------------------------------------------

def open_pursuit_channel(opp: dict[str, Any], brief_blocks: list[dict], owner_email: str | None,
                         extra_emails: list[str] | None = None) -> dict[str, Any]:
    """Create #rfp-<slug>, invite owner (+extras), post and pin the brief, set topic.

    Returns {"channel_id", "channel_name", "url"} or {} when the bot is not configured.
    """
    if not bot_enabled():
        return {}
    agency = (opp.get("agency") or "").split(".")[0]
    name = slugify_channel(f"{agency} {opp.get('title', '')}"[:60])
    channel_id, channel_name = create_channel(name)

    users = [lookup_user_id(owner_email)] + [lookup_user_id(e) for e in (extra_emails or [])]
    invite(channel_id, [u for u in users if u])

    topic_bits = [f"Due {opp.get('response_deadline')}" if opp.get("response_deadline") else "",
                  opp.get("url") or ""]
    set_topic(channel_id, " · ".join(b for b in topic_bits if b))

    ts = post(channel_id, f"Pursuing: {opp.get('title', 'RFP')}", brief_blocks)
    pin(channel_id, ts)
    return {"channel_id": channel_id, "channel_name": channel_name, "url": channel_url(channel_id)}


def post_pursuit_update(channel_id: str | None, text: str, blocks: list[dict] | None = None,
                        fallback_payload: dict[str, Any] | None = None) -> bool:
    """Post to the pursuit channel; fall back to the webhook when there is no channel."""
    if channel_id and bot_enabled():
        return post(channel_id, text, blocks) is not None
    if fallback_payload is not None:
        return _webhook(fallback_payload)
    if SLACK_DIGEST_CHANNEL and bot_enabled():
        return post(SLACK_DIGEST_CHANNEL, text, blocks) is not None
    return _webhook({"text": text, **({"blocks": blocks} if blocks else {})})


def close_pursuit_channel(channel_id: str | None, final_text: str) -> None:
    if not (channel_id and bot_enabled()):
        return
    post(channel_id, final_text)
    if SLACK_ARCHIVE_ON_CLOSE:
        archive(channel_id)


# ---------------------------------------------------------------------------
# Daily LOB digest
# ---------------------------------------------------------------------------

def build_digest_blocks(new_opps: list[dict[str, Any]], scanned_sources: int, fetched: int,
                        in_flight: list[dict[str, Any]] | None = None) -> list[dict]:
    from oppos.scoring.lobs import lob_label

    by_lob: dict[str, list[dict]] = {}
    for o in new_opps:
        by_lob.setdefault(o.get("lob") or "unrouted", []).append(o)
    lob_line = "  ·  ".join(f"*{lob_label(k) or k}* {len(v)}" for k, v in sorted(by_lob.items(), key=lambda kv: -len(kv[1])))

    blocks: list[dict] = [
        {"type": "header", "text": {"type": "plain_text", "text": f"OppOS scan — {len(new_opps)} new high-fit"}},
        {"type": "context", "elements": [{"type": "mrkdwn",
                                          "text": f"{scanned_sources} sources · {fetched} listings · " + (lob_line or "no new fits")}]},
    ]
    top = sorted(new_opps, key=lambda o: -int(o.get("fit_score") or 0))[:8]
    if top:
        lines = []
        for o in top:
            title = (o.get("title") or "Untitled")[:90]
            link = f"<{o['url']}|{title}>" if o.get("url") else title
            dl = f" · due {o['response_deadline'][:10]}" if o.get("response_deadline") else ""
            lines.append(f"*{int(o.get('fit_score') or 0)}* · {lob_label(o.get('lob')) or '—'} · {link} — {o.get('agency', '')}{dl}")
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(lines)[:2900]}})
    if in_flight:
        blocks.append({"type": "divider"})
        flight_lines = []
        for r in in_flight[:12]:
            link = f"<{r['url']}|{r['title'][:70]}>" if r.get("url") else r["title"][:70]
            due = f" · due {r['due']}" if r.get("due") else ""
            flight_lines.append(f"• *{r['owner']}* — {r['stage']} · {r['lob']} · {link}{due} · ✅ {r['checklist']}")
        blocks.append({"type": "section", "text": {"type": "mrkdwn",
                                                   "text": f"*In flight ({len(in_flight)})*\n" + "\n".join(flight_lines)[:2800]}})
    return blocks


def send_digest(new_opps: list[dict[str, Any]], scanned_sources: int, fetched: int,
                in_flight: list[dict[str, Any]] | None = None) -> bool:
    blocks = build_digest_blocks(new_opps, scanned_sources, fetched, in_flight)
    text = f"OppOS scan — {len(new_opps)} new high-fit opportunities"
    if bot_enabled() and SLACK_DIGEST_CHANNEL:
        return post(SLACK_DIGEST_CHANNEL, text, blocks) is not None
    return _webhook({"text": text, "blocks": blocks})
