"""Start a scan from the dashboard without holding the page, and report where it stands.

Two ways to run it:

* **On GitHub** (when ``GITHUB_TOKEN`` is set — a fine-grained token with Actions read/write on ``GITHUB_REPO``):
  the app starts the same ``scan.yml`` workflow the daily schedule runs, which has the headless browser some state
  portals need; status comes from the GitHub API.
* **In the app** otherwise: ``run_scan`` in a background thread, progress kept in meta (``scan_job``) so every
  viewer sees it. Portals that need a browser return nothing there (Streamlit Cloud has none).
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timedelta
from typing import Any

import httpx

from oppos.storage.db import get_meta, set_meta

logger = logging.getLogger(__name__)

GITHUB_REPO = os.environ.get("GITHUB_REPO", "brperdomo/OppOS")
WORKFLOW = "scan.yml"
_KEY = "scan_job"
_STALE = timedelta(minutes=90)  # the workflow's own timeout
_LOCK = threading.Lock()


def _token() -> str:
    return os.environ.get("GITHUB_TOKEN", "").strip()


def runs_on_github() -> bool:
    return bool(_token())


def _gh(method: str, path: str, **kw: Any) -> httpx.Response:
    return httpx.request(method, f"https://api.github.com/repos/{GITHUB_REPO}{path}", timeout=20,
                         headers={"Authorization": f"Bearer {_token()}", "Accept": "application/vnd.github+json"}, **kw)


def _job() -> dict[str, Any]:
    try:
        return json.loads(get_meta(_KEY) or "{}") or {}
    except (TypeError, ValueError):
        return {}


def _save(**fields: Any) -> None:
    job = _job()
    job.update(fields, updated=datetime.utcnow().isoformat())
    set_meta(_KEY, json.dumps(job))


def status() -> dict[str, Any]:
    """{state: idle | queued | running | done | failed, where, started, by, done, total, current, url, summary}."""
    job = _job()
    if not job:
        return {"state": "idle"}
    if job.get("where") == "github" and job.get("state") in ("queued", "running"):
        try:
            runs = _gh("GET", f"/actions/workflows/{WORKFLOW}/runs", params={"per_page": 5, "event": "workflow_dispatch"}).json()
            run = next((r for r in runs.get("workflow_runs", []) if r.get("created_at", "") >= job.get("started", "")[:19]), None)
            if run:
                state = {"queued": "queued", "in_progress": "running", "completed": "done"}.get(run.get("status"), "running")
                if state == "done" and run.get("conclusion") != "success":
                    state = "failed"
                if state != job.get("state") or run.get("html_url") != job.get("url"):
                    _save(state=state, url=run.get("html_url"))
                job.update(state=state, url=run.get("html_url"))
        except Exception as e:  # the status line falls back to what was recorded
            logger.warning("GitHub run status failed: %s", e)
    if job.get("state") in ("queued", "running"):
        try:
            if datetime.utcnow() - datetime.fromisoformat(job.get("updated") or job.get("started") or "") > _STALE:
                job["state"] = "failed"
                job["error"] = "no progress for 90 minutes"
        except ValueError:
            pass
    return job


def start(by: str, sources: list[str] | None = None) -> tuple[bool, str]:
    """Start a scan unless one is running. Returns (started, message)."""
    with _LOCK:
        if status().get("state") in ("queued", "running"):
            return False, "A scan is already running."
        now = datetime.utcnow().isoformat()
        if runs_on_github():
            inputs = {"sources": ",".join(sources)} if sources else {}
            r = _gh("POST", f"/actions/workflows/{WORKFLOW}/dispatches", json={"ref": "main", "inputs": inputs})
            if r.status_code >= 300:
                return False, f"GitHub refused to start the scan ({r.status_code}): {r.text[:160]}"
            set_meta(_KEY, json.dumps({"state": "queued", "where": "github", "started": now, "updated": now, "by": by,
                                       "sources": sources or []}))
            return True, "Scan started on GitHub — usually 10–20 minutes."
        set_meta(_KEY, json.dumps({"state": "running", "where": "app", "started": now, "updated": now, "by": by,
                                   "done": 0, "total": 0, "current": "", "sources": sources or []}))

    def run() -> None:
        from oppos.pipeline import run_scan
        from oppos.sources.registry import _load_registry
        try:
            reg = _load_registry()
            picked = [(k, reg[k][0], reg[k][1]) for k in (sources or []) if k in reg] or None
            stats = run_scan(sources=picked, on_progress=lambda i, n, name: _save(done=i, total=n, current=name))
            _save(state="done", finished=datetime.utcnow().isoformat(), current="",
                  summary=f"{stats.get('fetched', 0):,} listings checked, {stats.get('new', 0)} new, {stats.get('scored', 0)} scored as a fit"
                          + (f", {len(stats.get('errors') or [])} source errors" if stats.get("errors") else ""))
        except Exception as e:
            logger.exception("Scan failed")
            _save(state="failed", error=f"{type(e).__name__}: {e}"[:200])

    threading.Thread(target=run, name="oppos-scan", daemon=True).start()
    return True, "Scan started — it runs in the background; keep working."
