"""An RFP's documents, read once and kept: download → read (Nutrient Processor API) → store → digest →
requirements (Nutrient Data Extraction) → re-score.

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
from oppos.storage.db import _execute, add_pursuit_event, get_documents, get_meta, save_document, set_document_info, set_meta

logger = logging.getLogger(__name__)

DRAFT_BUDGET = 150_000    # characters kept on the opportunity row (the drafter's budget)
SCORING_BUDGET = 60_000   # characters the fit scorer reads
_JOB_STALE = timedelta(minutes=50)  # reading plus requirements extraction of a large RFP
_LOCK = threading.Lock()
ACTOR = "OppOS"  # activity entries for what the app does by itself


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
            add_pursuit_event(sid, ACTOR, "docs_fetch_failed", f"Couldn't get the RFP's files from the listing: {type(e).__name__}: {e}"[:300])
            files = []
        if files:
            add_pursuit_event(sid, ACTOR, "docs_fetched", f"Got {len(files)} file{'s' if len(files) != 1 else ''} from the listing: "
                              + ", ".join(f.name for f in files[:8]) + (" …" if len(files) > 8 else ""))
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
        if r["status"] == "read" and r["text"].strip():
            set_document_info(sid, f.name, summary=summarize(f.name, r["text"]))
        new += 1
    for d in get_documents(sid, with_text=True):  # documents read before summaries existed
        if d["status"] == "read" and not d.get("summary") and (d.get("text") or "").strip():
            set_document_info(sid, d["name"], summary=summarize(d["name"], d["text"]))
    docs = get_documents(sid)
    if new:
        failed = [d["name"] for d in docs if d["status"] == "failed"]
        add_pursuit_event(sid, ACTOR, "docs_read", f"Read {new} document{'s' if new != 1 else ''} with the Nutrient Processor API "
                          f"({sum(1 for d in docs if d['status'] == 'read')} of {len(docs)} now read)"
                          + (f"; couldn't read {', '.join(failed[:4])}" if failed else ""))
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


def summarize(name: str, text: str) -> str:
    """One plain sentence: what this document is and what it asks of the vendor (Claude Haiku, first ~12k characters)."""
    try:
        from oppos.config import SCORING_MODEL_STAGE1
        from oppos.scoring.qualifier import _get_client
        from oppos.sources.extract_text import compact
        resp = _get_client().messages.create(
            model=SCORING_MODEL_STAGE1, max_tokens=120,
            messages=[{"role": "user", "content": f"Document '{name}' from a public-sector RFP package. In one plain sentence of at most 30 words, "
                       "say what this document is and what it asks a vendor to do or provide. No preamble.\n\n" + compact(text)[:12000]}])
        return " ".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()[:400]
    except Exception as e:
        logger.warning("Summary for %s failed: %s", name, e)
        return ""


def _signature(source_id: str) -> str:
    """Which documents (name and size) a stored extraction was made from: new or changed files make it stale."""
    return "|".join(f"{d['name']}:{d.get('size')}" for d in get_documents(source_id) if d["status"] == "read")


def stored_extraction(source_id: str) -> dict[str, Any] | None:
    """The requirements extraction for these documents, or None when there is none or the documents changed."""
    raw = get_meta(f"extraction:{source_id}")
    try:
        ext = json.loads(raw) if raw else None
    except (TypeError, ValueError):
        return None
    return ext if ext and ext.get("signature") == _signature(source_id) else None


def _add_matrices(sid: str, ext: dict[str, Any], save: bool = True) -> int:
    """Requirements matrices read from the documents' own text (Data Extraction often misses spreadsheet rows)."""
    from oppos.drafting.extraction import add_matrices
    docs = [(d["name"], d.get("text") or "") for d in get_documents(sid, with_text=True) if d["status"] == "read"]
    added = add_matrices(ext, docs)
    for name in (ext.get("answer_columns") or {}):
        set_document_info(sid, name, doc_type="requirements_matrix")
    if added:
        add_pursuit_event(sid, ACTOR, "matrix_read", f"Read {added} requirements row by row from the requirements matri"
                          f"{'ces' if len(ext.get('answer_columns') or {}) > 1 else 'x'}: {', '.join(ext.get('answer_columns') or {})}"[:500])
    if save:
        set_meta(f"extraction:{sid}", json.dumps(ext))
    return added


def extract_requirements(opp: dict[str, Any], on_progress: Callable[[str], None] | None = None) -> dict[str, Any] | None:
    """Data Extraction over every document read: requirements, dates, how to submit, forms, evaluation criteria —
    page-cited. Stored in meta (extraction:<id>) so the RFP tab, the facts and the drafter share one run."""
    from oppos.drafting.extraction import CHARS_PER_PAGE_ESTIMATE, extract_rfp_requirements, extraction_available
    sid = str(opp.get("source_id") or "")
    if not extraction_available():
        return None
    have = stored_extraction(sid)
    if have and not have.get("matrices_checked"):  # extractions made before requirements matrices were read
        _add_matrices(sid, have)
    if have:
        known = {d["name"]: d for d in get_documents(sid)}
        for f in have.get("files") or []:  # extractions made before document types were stored
            if f.get("file") in known and not known[f["file"]].get("doc_type"):
                set_document_info(sid, f["file"], doc_type=f.get("document_type") or "other")
        return have
    docs = {d["name"]: d for d in get_documents(sid) if d["status"] == "read"}
    files = [f for f in local_files(sid) if f.name in docs]
    if not files:
        return None
    hints = {name: d.get("pages") or max(1, int(d.get("chars") or 0) // CHARS_PER_PAGE_ESTIMATE) for name, d in docs.items()}
    ext = extract_rfp_requirements(files, on_progress=on_progress, page_hints=hints)
    _add_matrices(sid, ext, save=False)  # before the check: a package can be all matrix and no prose
    if ext.get("requirements") or ext.get("solicitation"):
        ext["signature"] = _signature(sid)
        ext["extracted_at"] = datetime.utcnow().isoformat()
        set_meta(f"extraction:{sid}", json.dumps(ext))
        counts: dict[str, int] = {}
        for r in ext.get("requirements") or []:
            counts[r.get("file", "")] = counts.get(r.get("file", ""), 0) + 1
        for f in ext.get("files") or []:
            set_document_info(sid, f["file"], doc_type=f.get("document_type") or "other")
        st_ = ext.get("stats") or {}
        add_pursuit_event(sid, ACTOR, "requirements_extracted",
                          f"Nutrient Data Extraction pulled {st_.get('requirements', 0)} requirements ({st_.get('mandatory', 0)} mandatory) "
                          f"from {len(ext.get('files') or [])} documents, {ext.get('pages', 0)} pages · {ext.get('credits_cost', 0):,} credits"
                          + (f"; not extracted: {'; '.join((ext.get('skipped') or []) + (ext.get('errors') or []))[:200]}"
                             if ext.get("skipped") or ext.get("errors") else ""))
    elif ext.get("errors"):
        add_pursuit_event(sid, ACTOR, "requirements_failed", "Data Extraction failed: " + "; ".join(ext["errors"])[:300])
    return ext


def rescore(opp: dict[str, Any]) -> dict[str, Any] | None:
    """Re-score the fit on the documents (the listing alone is often a title and a date)."""
    from oppos.scoring.qualifier import qualify
    from oppos.storage.db import upsert_opportunity
    text = digest_for(opp.get("source_id", ""), SCORING_BUDGET)
    if not text:
        return None
    before = int(float(opp.get("fit_score") or 0))
    scored = qualify(dict(opp), attachment_text=text)
    scored["attachment_text"] = None  # keep the stored digest (the upsert only replaces it when given one)
    upsert_opportunity(scored)
    n = ((scored.get("stage2") or {}).get("basis") or {}).get("documents") or 0
    add_pursuit_event(opp.get("source_id", ""), ACTOR, "rescored",
                      f"Fit re-scored on the listing and {n} document{'s' if n != 1 else ''}: {before} → {int(scored.get('fit_score') or 0)}")
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
        _set_job(sid, state="reading", phase="reading", done=0, total=0, current="", error="", extracted=None,
                 started=datetime.utcnow().isoformat())

    def run() -> None:
        try:
            res = read_rfp_documents(dict(opp), on_progress=lambda name, i, n: _set_job(sid, current=name, done=i, total=n))
            changed = bool(res["new"])
            _set_job(sid, summarized=True, matrices=True)
            if res["read"]:
                _set_job(sid, phase="requirements", current="pulling out the requirements")
                try:
                    changed = changed or stored_extraction(sid) is None
                    ext = extract_requirements(dict(opp), on_progress=lambda msg: _set_job(sid, current=msg))
                    _set_job(sid, extracted=bool(ext and (ext.get("requirements") or ext.get("solicitation"))),
                             extract_errors=(ext or {}).get("errors", [])[:5])
                except Exception as e:  # the documents are read either way; the draft can extract again
                    logger.warning("Requirements extraction for %s failed: %s", sid, e)
                    _set_job(sid, extracted=False, extract_errors=[f"{type(e).__name__}: {e}"[:200]])
            if rescore_after and res["read"] and changed:  # nothing new read or extracted: the score stands
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
