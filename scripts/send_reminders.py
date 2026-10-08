#!/usr/bin/env python3
"""Deadline and inactivity reminders for active pursuits — run daily by GitHub Actions.

For each active pursuit, posts the single most urgent unsent reminder to its
Slack channel (or the digest channel / webhook when there is none):
  T-14, T-7, T-3, T-1, due today, overdue   (submission deadline)
  Q-3, Q-1                                  (questions deadline)
  stale                                     (no activity for 7+ days; at most once per week)

Usage:
    python scripts/send_reminders.py            # send
    python scripts/send_reminders.py --dry-run  # print what would be sent
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import oppos.config  # noqa: F401
from oppos.outputs import slack_pursuits as sp
from oppos.pursuits import days_until
from oppos.storage.db import (
    add_pursuit_event,
    get_opps_by_ids,
    init_db,
    last_pursuit_activity,
    list_pursuits,
    mark_reminder_sent,
    reminder_sent,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("oppos.reminders")

_DEADLINE_STEPS = [(-1, "overdue", "⚠️ *Overdue* — the submission deadline has passed"),
                   (0, "due", "🚨 *Due today*"),
                   (1, "t1", "🔴 Due *tomorrow*"),
                   (3, "t3", "🟠 Due in *3 days*"),
                   (7, "t7", "🟡 Due in *7 days*"),
                   (14, "t14", "🗓️ Due in *2 weeks*")]
_QA_STEPS = [(1, "q1", "❓ Questions due *tomorrow*"), (3, "q3", "❓ Questions due in *3 days*")]
_STALE_DAYS = 7


def _owner_mention(pursuit: dict) -> str:
    uid = sp.lookup_user_id(pursuit.get("owner_email"))
    return f"<@{uid}>" if uid else (pursuit.get("owner_name") or pursuit.get("owner_email") or "owner")


def _pick(pursuit: dict, opp: dict) -> tuple[str, str] | None:
    """Return (kind, message) for the most urgent unsent reminder, or None."""
    sid = pursuit["source_id"]
    title = (opp.get("title") or "RFP")[:120]
    link = f"<{opp['url']}|{title}>" if opp.get("url") else title
    who = _owner_mention(pursuit)

    # Steps are ordered most-urgent first; pick the ONE that applies today and send it only
    # if it has not been sent. Never fall back to a less urgent step (e.g. "due in 3 days"
    # must not fire after the deadline has passed).
    # Reminder keys include the deadline they were sent for, so extending a deadline
    # re-arms the T-x reminders for the new date.
    due_raw = pursuit.get("submission_deadline") or str(opp.get("response_deadline") or "")[:10]
    d = days_until(due_raw)
    if d is not None:
        step = next(((kind, label) for threshold, kind, label in _DEADLINE_STEPS if d <= threshold), None)
        if step:
            key = f"{step[0]}@{due_raw}"
            if not reminder_sent(sid, key):
                return key, f"{step[1]} ({due_raw}) — {link}\n{who}"

    qa_raw = pursuit.get("qa_deadline")
    q = days_until(qa_raw)
    if q is not None:
        step = next(((kind, label) for threshold, kind, label in _QA_STEPS if q <= threshold), None)
        if step:
            key = f"{step[0]}@{qa_raw}"
            if not reminder_sent(sid, key):
                return key, f"{step[1]} ({qa_raw}) — {link}\n{who}"

    last = last_pursuit_activity(sid)
    if last:
        try:
            idle = (datetime.utcnow() - datetime.fromisoformat(last)).days
        except ValueError:
            idle = 0
        kind = f"stale-{date.today().isocalendar()[1]}"
        if idle >= _STALE_DAYS and not reminder_sent(sid, kind):
            return kind, f"💤 No activity on *{title}* for {idle} days — still pursuing? {who}"
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    init_db()
    pursuits = list_pursuits(status="active")
    opps = get_opps_by_ids([p["source_id"] for p in pursuits])
    sent = 0
    for p in pursuits:
        opp = opps.get(p["source_id"])
        if not opp:
            continue
        picked = _pick(p, opp)
        if not picked:
            continue
        kind, msg = picked
        if args.dry_run:
            print(f"[dry-run] {p['source_id']} {kind}: {msg}")
            continue
        ok = sp.post_pursuit_update(p.get("slack_channel_id"), msg)
        if ok:
            mark_reminder_sent(p["source_id"], kind)
            add_pursuit_event(p["source_id"], "system", "reminder", kind)
            sent += 1
        else:
            logger.warning("Reminder not delivered for %s (%s) — Slack not configured?", p["source_id"], kind)
    logger.info("Reminders: %d active pursuits, %d sent", len(pursuits), sent)


if __name__ == "__main__":
    main()
