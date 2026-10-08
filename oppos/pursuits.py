"""Pursuit domain logic — a pursuit is an RFP someone has committed to work.

Owns the lifecycle (start → submitted → won/lost/abandoned), the go/no-go
checklist, portal-registration lookup, and the Slack/Notion side effects, so
the dashboard only renders state and calls these functions.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from oppos.outputs import slack_pursuits as sp
from oppos.outputs.slack_alerts import _build_abandon_message, _build_pursue_message
from oppos.storage.db import (
    _parse_deadline,
    add_pursuit_event,
    create_pursuit,
    get_portal_registration,
    get_pursuit,
    set_pipeline_status,
    update_pursuit,
)

logger = logging.getLogger(__name__)

# key → label. Order is the order shown in the UI.
CHECKLIST: list[tuple[str, str]] = [
    ("go_no_go", "Go / no-go decided"),
    ("registration", "Vendor registration confirmed"),
    ("questions", "Questions submitted (Q&A)"),
    ("salesforce", "Salesforce opp created"),
    ("draft", "Response draft started"),
    ("security", "Security / compliance answers reviewed"),
    ("pricing", "Pricing approved"),
    ("legal", "Legal / T&Cs reviewed"),
    ("final", "Final review complete"),
]

SUBMISSION_METHODS = ["unknown", "portal", "email", "mail", "in_person"]
REGISTRATION_STATUSES = ["unknown", "registered", "in_progress", "not_registered", "not_required"]
REGISTRATION_LABELS = {
    "registered": "Registered",
    "in_progress": "Registration in progress",
    "not_registered": "Registration needed",
    "not_required": "No registration required",
    "unknown": "Registration unknown",
}
CLOSED_STATUSES = ("submitted", "won", "lost", "abandoned")


class PursuitOwnedError(PermissionError):
    """Raised when a user tries to take over a pursuit that someone else holds."""

    def __init__(self, pursuit: dict[str, Any]):
        self.pursuit = pursuit
        owner = pursuit.get("owner_name") or pursuit.get("owner_email") or "someone else"
        super().__init__(f"Owned by {owner} ({stage_label(pursuit.get('status'))}) — ask them to release it first.")


def owned_by_other(pursuit: dict[str, Any] | None, user: dict[str, Any]) -> bool:
    if not pursuit or pursuit.get("status") not in OPEN_STAGES:
        return False
    return (pursuit.get("owner_email") or "").lower() != (user.get("email") or "").lower()

# Canonical stage model. Everything after "new" has an owner.
#   new → evaluating (claimed) → active (pursuing) → submitted → won | lost ; exits: abandoned, released
STAGES: dict[str, str] = {
    "evaluating": "Claimed",
    "active": "Pursuing",
    "submitted": "Submitted",
    "won": "Won",
    "lost": "Lost",
    "abandoned": "Abandoned",
    "released": "Released",
}
OPEN_STAGES = ("evaluating", "active")


def stage_label(status: str | None) -> str:
    return STAGES.get(status or "", (status or "").title())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def deadline_date(raw: str | None) -> date | None:
    dt = _parse_deadline(raw) if raw else None
    if dt is None and raw:
        try:
            dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            return None
    return dt.date() if dt else None


def days_until(raw: str | None) -> int | None:
    d = deadline_date(raw)
    return (d - date.today()).days if d else None


def registration_for_source(source: str | None) -> dict[str, Any] | None:
    """Portal registration row for an opportunity's source, if any."""
    if not source:
        return None
    return get_portal_registration(source)


def registration_badge(reg: dict[str, Any] | None) -> tuple[str, str] | None:
    """(label, css_class) for a card badge, or None when nothing useful is known."""
    if not reg:
        return None
    status = reg.get("status") or "unknown"
    if status == "unknown":
        return None
    lead = reg.get("lead_time_days")
    label = REGISTRATION_LABELS.get(status, status)
    if status in ("not_registered", "in_progress") and lead not in (None, "", 0, "0"):
        label += f" · ~{lead}d"
    css = {"registered": "reg-ok", "not_required": "reg-ok", "in_progress": "reg-warn", "not_registered": "reg-bad"}[status]
    return label, css


def checklist_state(pursuit: dict[str, Any] | None) -> dict[str, bool]:
    import json
    raw = (pursuit or {}).get("checklist_json") or "{}"
    try:
        data = json.loads(raw) if isinstance(raw, str) else dict(raw)
    except json.JSONDecodeError:
        data = {}
    return {key: bool(data.get(key)) for key, _ in CHECKLIST}


def checklist_progress(pursuit: dict[str, Any] | None) -> tuple[int, int]:
    state = checklist_state(pursuit)
    return sum(1 for v in state.values() if v), len(state)


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

def claim_opportunity(opp: dict[str, Any], user: dict[str, Any], note: str = "") -> dict[str, Any]:
    """"Grab" an RFP: the user becomes owner and it enters the evaluating stage.

    The pipeline status is left alone (new/qualified/expiring_soon) so scoring
    flows still apply; the claim is visible everywhere via the owner chip and
    the team board. Slack gets a one-liner in the digest channel if configured.
    """
    sid = opp["source_id"]
    owner_email = (user.get("email") or "").lower()
    owner_name = user.get("name") or owner_email
    existing = get_pursuit(sid)
    if existing and existing.get("status") in OPEN_STAGES:
        return existing  # already owned — caller decides how to surface that

    set_pipeline_status(sid, opp.get("pipeline_status") or "new", notes=note or None, assigned_to=owner_name)
    reg = registration_for_source(opp.get("source"))
    fields = {
        "owner_email": owner_email, "owner_name": owner_name, "lob": opp.get("lob"),
        "reason": note or "Claimed for evaluation", "status": "evaluating",
        "submission_deadline": (opp.get("response_deadline") or "")[:10] or None,
        "registration_status": (reg or {}).get("status") or "unknown", "portal": opp.get("source"),
        "notion_page_id": opp.get("notion_page_id"), "created_by": owner_email, "closed_at": None,
    }
    if existing:
        update_pursuit(sid, **{k: v for k, v in fields.items() if k != "created_by"})
    else:
        create_pursuit(sid, **fields)
    add_pursuit_event(sid, owner_email, "claimed", note or "Claimed for evaluation")
    try:
        if sp.bot_enabled() and sp.SLACK_DIGEST_CHANNEL:
            link = f"<{opp['url']}|{opp.get('title', 'RFP')[:100]}>" if opp.get("url") else opp.get("title", "RFP")[:100]
            sp.post(sp.SLACK_DIGEST_CHANNEL, f"👋 {owner_name} claimed *{link}* for evaluation")
    except Exception as e:
        logger.info("Slack claim notice failed: %s", e)
    return get_pursuit(sid) or {}


def release_claim(opp: dict[str, Any], user: dict[str, Any], reason: str = "") -> None:
    """Un-claim an evaluating RFP so someone else can pick it up."""
    sid = opp["source_id"]
    set_pipeline_status(sid, opp.get("pipeline_status") or "new", notes=reason or None, assigned_to="")
    update_pursuit(sid, status="released", closed_at=datetime.utcnow().isoformat())
    add_pursuit_event(sid, user.get("email", ""), "released", reason or "Released back to the pool")


def board_rows(pursuits: list[dict[str, Any]], opps: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten open pursuits for the team board / Slack 'in flight' section."""
    from oppos.scoring.lobs import lob_label
    from oppos.storage.db import last_pursuit_activity

    rows = []
    for p in pursuits:
        o = opps.get(p["source_id"]) or {}
        done, total = checklist_progress(p)
        due = p.get("submission_deadline") or (o.get("response_deadline") or "")[:10]
        rows.append({
            "source_id": p["source_id"],
            "owner": p.get("owner_name") or p.get("owner_email") or "—",
            "stage": stage_label(p.get("status")),
            "lob": lob_label(p.get("lob") or o.get("lob")) or "—",
            "title": o.get("title") or "Untitled",
            "agency": o.get("agency") or "",
            "url": o.get("url") or "",
            "due": due or "",
            "days_left": days_until(due),
            "checklist": f"{done}/{total}",
            "last_activity": (last_pursuit_activity(p["source_id"]) or p.get("updated_at") or "")[:10],
        })
    rows.sort(key=lambda r: (r["days_left"] if r["days_left"] is not None else 9999, r["owner"]))
    return rows

def start_pursuit(opp: dict[str, Any], reason: str, user: dict[str, Any],
                  notion_url: str = "", notion_page_id: str | None = None) -> dict[str, Any]:
    """Create the pursuit record, move the opp to in_progress, open Slack (channel or alert).

    Returns {"pursuit", "slack_channel_name", "slack_url", "slack_alert_sent"}.
    """
    sid = opp["source_id"]
    reason = reason or "Qualified — pursuing"
    owner_email = (user.get("email") or "").lower()
    owner_name = user.get("name") or owner_email

    existing = get_pursuit(sid)
    if owned_by_other(existing, user):
        raise PursuitOwnedError(existing)

    set_pipeline_status(sid, "in_progress", notes=reason, assigned_to=owner_name)

    if existing and existing.get("status") in OPEN_STAGES:
        # Promote an existing claim: keep everything the owner already filled in
        # (deadlines, registration, method, checklist, next action); only fill gaps.
        promote: dict[str, Any] = {"status": "active", "reason": reason, "closed_at": None}
        if notion_page_id:
            promote["notion_page_id"] = notion_page_id
        for key, value in (
            ("lob", opp.get("lob")),
            ("portal", opp.get("source")),
            ("submission_deadline", (opp.get("response_deadline") or "")[:10] or None),
            ("owner_email", owner_email),
            ("owner_name", owner_name),
        ):
            if not existing.get(key) and value:
                promote[key] = value
        update_pursuit(sid, **promote)
    else:
        reg = registration_for_source(opp.get("source"))
        fields = {
            "owner_email": owner_email,
            "owner_name": owner_name,
            "lob": opp.get("lob"),
            "reason": reason,
            "status": "active",
            "submission_deadline": (opp.get("response_deadline") or "")[:10] or None,
            "registration_status": (reg or {}).get("status") or "unknown",
            "portal": opp.get("source"),
            "notion_page_id": notion_page_id or opp.get("notion_page_id"),
            "created_by": owner_email,
            "closed_at": None,
        }
        if existing:  # a closed/released record — reuse the row
            update_pursuit(sid, **{k: v for k, v in fields.items() if k != "created_by"})
        else:
            create_pursuit(sid, **fields)
    add_pursuit_event(sid, owner_email, "started", reason)

    result: dict[str, Any] = {"slack_channel_name": "", "slack_url": "", "slack_alert_sent": False}
    brief = _build_pursue_message(opp, reason=reason, notion_url=notion_url)["blocks"]
    try:
        if sp.bot_enabled():
            ch = sp.open_pursuit_channel(opp, brief, owner_email)
            if ch:
                update_pursuit(sid, slack_channel_id=ch["channel_id"], slack_channel_name=ch["channel_name"])
                add_pursuit_event(sid, "system", "slack_channel", f"#{ch['channel_name']}")
                result.update(slack_channel_name=ch["channel_name"], slack_url=ch["url"])
            # Also drop a one-liner in the digest channel so the team sees new pursuits
            if sp.SLACK_DIGEST_CHANNEL:
                link = f"<{ch['url']}|#{ch['channel_name']}>" if ch else ""
                sp.post(sp.SLACK_DIGEST_CHANNEL, f"🎯 {owner_name} is pursuing *{opp.get('title', 'RFP')[:120]}* {link}".strip())
        else:
            from oppos.outputs.slack_alerts import send_pursue_alert
            result["slack_alert_sent"] = send_pursue_alert(opp, reason=reason, notion_url=notion_url)
    except Exception as e:  # Slack must never block a pursuit
        logger.error("Slack setup failed for %s: %s", sid, e)
        add_pursuit_event(sid, "system", "slack_error", str(e)[:300])

    result["pursuit"] = get_pursuit(sid)
    return result


def save_pursuit_fields(sid: str, user: dict[str, Any], **fields: Any) -> None:
    """Persist edited pursuit fields and log a compact change event."""
    before = get_pursuit(sid) or {}
    changed = {k: v for k, v in fields.items() if (before.get(k) or None) != (v or None)}
    if not changed:
        return
    update_pursuit(sid, **changed)
    summary = ", ".join(f"{k}={v}" for k, v in changed.items() if k != "checklist_json")
    if "checklist_json" in changed:
        summary = (summary + ", " if summary else "") + "checklist updated"
    add_pursuit_event(sid, user.get("email", ""), "updated", summary[:300])


def transition_pursuit(opp: dict[str, Any], new_status: str, user: dict[str, Any], reason: str = "") -> None:
    """submitted | won | lost | abandoned — updates pipeline, pursuit, Notion, Slack."""
    assert new_status in CLOSED_STATUSES, new_status
    sid = opp["source_id"]
    pipeline_status = "lost" if new_status == "abandoned" else new_status
    default_reason = {
        "submitted": "Response submitted",
        "won": "Awarded",
        "lost": "Not awarded",
        "abandoned": "Abandoned after pursuit",
    }[new_status]
    reason = reason or default_reason

    set_pipeline_status(sid, pipeline_status, notes=reason)
    update_pursuit(sid, status=new_status, closed_at=None if new_status == "submitted" else datetime.utcnow().isoformat())
    add_pursuit_event(sid, user.get("email", ""), new_status, reason)

    try:
        from oppos.outputs.notion_sync import update_pipeline_status
        update_pipeline_status(sid, pipeline_status, notes=reason)
    except Exception as e:
        logger.warning("Notion status sync failed for %s: %s", sid, e)

    pursuit = get_pursuit(sid) or {}
    channel_id = pursuit.get("slack_channel_id")
    emoji = {"submitted": "📨", "won": "🏆", "lost": "📉", "abandoned": "🚫"}[new_status]
    text = f"{emoji} *{new_status.title()}* — {opp.get('title', 'RFP')[:120]}\n_{reason}_ — {user.get('name') or user.get('email', '')}"
    try:
        if new_status == "submitted":
            sp.post_pursuit_update(channel_id, text)
            if sp.SLACK_DIGEST_CHANNEL and sp.bot_enabled():
                sp.post(sp.SLACK_DIGEST_CHANNEL, text)
        else:
            label = {"won": "Won", "lost": "Lost", "abandoned": "Abandoned"}[new_status]
            fallback = _build_abandon_message(opp, reason=reason, label=label) if new_status != "won" else {"text": text}
            if channel_id and sp.bot_enabled():
                sp.close_pursuit_channel(channel_id, text)
                if sp.SLACK_DIGEST_CHANNEL:
                    sp.post(sp.SLACK_DIGEST_CHANNEL, text)
            else:
                sp.post_pursuit_update(None, text, fallback_payload=fallback)
    except Exception as e:
        logger.error("Slack update failed for %s: %s", sid, e)
