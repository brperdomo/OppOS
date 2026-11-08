"""An RFP's documents, read once and kept: download → read (Nutrient Processor API) → store → digest → re-score.

`read_rfp_documents` does the work; `start_reading` runs it in the background (used when someone grabs an RFP)
and records progress in meta under `docs_job:<source_id>`, which the dashboard polls.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from oppos.sources.attachments import ATTACHMENTS_DIR, _sanitize_filename, download_attachments
from oppos.sources.extract_text import build_digest, read_file
from oppos.storage.db import _execute, get_documents, get_meta, save_document, set_meta

logger = logging.getLogger(__name__)

DRAFT_BUDGET = 150_000    # characters kept on the opportunity row (the drafter's budget)
SCORING_BUDGET = 60_000   # characters the fit scorer reads
_JOB_STALE = timedelta(minutes=20)
_LOCK = threading.Lock()


def folder(source_id: str) -> Path:
    return ATTACHMENTS_DIR / _sanitize_filename(str(source_id or ""))


def local_files(source_id: str) -> list[Path]:
    d = folder(source_id)
    return sorted(f for f in d.iterdir() if f.is_file()) if d.is_dir() else []


def digest_for(source_id: str, budget: int) -> str:
    docs = get_documents(source_id, with_text=True)
    return build_digest([(d["name"], d.get("text") or "") for d in docs if d["status"] == "read"], budget)


def read_rfp_documents(opp: dict[str, Any], on_progress: Callable[[str, int, int], None] | None = None,
                       force: bool = False) -> dict[str, Any]:
    """Fetch the RFP's documents if none are on disk, read every one not read before, store the texts and the
    digest. Returns {files, read, unreadable, failed: [(name, note)], new}."""
    sid = str(opp.get("source_id") or "")
    files = local_files(sid)
    if not files:
        try:
            files = download_attachments(opp)
        except Exception as e:
            logger.warning("Downloading documents for %s failed: %s", sid, e)
            files = []
    known = {d["name"]: d for d in get_documents(sid)}
    new = 0
    for i, f in enumerate(files):
        prev = known.get(f.name)
        size = f.stat().st_size
        if prev and not force and prev["status"] in ("read", "unreadable") and int(prev.get("size") or 0) == size:
            continue  # already read this exact file
        if on_progress:
            on_progress(f.name, i, len(files))
        r = read_file(f)
        save_document(sid, f.name, size, r["pages"], r["chars"], r["status"], r["note"], r["text"])
        new += 1
    docs = get_documents(sid)
    digest = digest_for(sid, DRAFT_BUDGET)
    if digest:
        _execute("UPDATE opportunities SET attachment_text = ? WHERE source_id = ?", (digest, sid))
        opp["attachment_text"] = digest
    return {
        "files": len(docs),
        "read": sum(1 for d in docs if d["status"] == "read"),
        "unreadable": sum(1 for d in docs if d["status"] == "unreadable"),
        "failed": [(d["name"], d.get("note") or "") for d in docs if d["status"] == "failed"],
        "new": new,
    }


def rescore(opp: dict[str, Any]) -> dict[str, Any] | None:
    """Re-score the fit on the documents (the listing alone is often a title and a date)."""
    from oppos.scoring.qualifier import qualify
    from oppos.storage.db import upsert_opportunity
    text = digest_for(opp.get("source_id", ""), SCORING_BUDGET)
    if not text:
        return None
    scored = qualify(dict(opp), attachment_text=text)
    scored["attachment_text"] = None  # keep the stored digest (the upsert only replaces it when given one)
    upsert_opportunity(scored)
    return scored


# ---------------------------------------------------------------------------
# Background job
# ---------------------------------------------------------------------------

def job_status(source_id: str) -> dict[str, Any] | None:
    raw = get_meta(f"docs_job:{source_id}")
    try:
        job = json.loads(raw) if raw else None
    except (TypeError, ValueError):
        return None
    if job and job.get("state") == "reading":
        try:
            if datetime.utcnow() - datetime.fromisoformat(job.get("updated") or "") > _JOB_STALE:
                job["state"] = "failed"
                job["error"] = "stopped (the app restarted while reading)"
        except ValueError:
            pass
    return job


def _set_job(source_id: str, **fields: Any) -> None:
    job = job_status(source_id) or {}
    job.update(fields, updated=datetime.utcnow().isoformat())
    set_meta(f"docs_job:{source_id}", json.dumps(job))


def start_reading(opp: dict[str, Any], rescore_after: bool = True) -> bool:
    """Read the RFP's documents in a background thread. False when a read is already running for it."""
    sid = str(opp.get("source_id") or "")
    with _LOCK:
        job = job_status(sid)
        if job and job.get("state") == "reading":
            return False
        _set_job(sid, state="reading", done=0, total=0, current="", error="", started=datetime.utcnow().isoformat())

    def run() -> None:
        try:
            res = read_rfp_documents(dict(opp), on_progress=lambda name, i, n: _set_job(sid, current=name, done=i, total=n))
            if rescore_after and res["read"]:
                _set_job(sid, current="re-scoring the fit on the documents")
                try:
                    rescore(dict(opp))
                except Exception as e:  # the documents are read either way; a failed re-score keeps the old score
                    logger.warning("Re-score after reading %s failed: %s", sid, e)
            _set_job(sid, state="done", current="", done=res["files"], total=res["files"],
                     finished=datetime.utcnow().isoformat())
        except Exception as e:
            logger.exception("Reading documents for %s failed", sid)
            _set_job(sid, state="failed", error=f"{type(e).__name__}: {e}"[:200])

    threading.Thread(target=run, name=f"docs-{sid}", daemon=True).start()
    return True
