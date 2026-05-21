"""SQLite storage — uses Turso HTTP API (cloud) when configured, local file otherwise."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

import httpx

import oppos.config as _cfg

_USE_TURSO = bool(_cfg.TURSO_DATABASE_URL and _cfg.TURSO_AUTH_TOKEN)


def _turso_url() -> str:
    url = _cfg.TURSO_DATABASE_URL
    if url.startswith("libsql://"):
        url = url.replace("libsql://", "https://", 1)
    return url


def _turso_execute(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    """Execute a SQL statement against Turso via the HTTP API."""
    url = f"{_turso_url()}/v2/pipeline"
    args = []
    for p in params:
        if p is None:
            args.append({"type": "null", "value": None})
        elif isinstance(p, int):
            args.append({"type": "integer", "value": str(p)})
        elif isinstance(p, float):
            args.append({"type": "float", "value": p})
        else:
            args.append({"type": "text", "value": str(p)})

    body = {
        "requests": [
            {"type": "execute", "stmt": {"sql": sql, "args": args}},
            {"type": "close"},
        ]
    }
    headers = {"Authorization": f"Bearer {_cfg.TURSO_AUTH_TOKEN}"}

    resp = httpx.post(url, json=body, headers=headers, timeout=30.0)
    resp.raise_for_status()
    data = resp.json()

    result = data.get("results", [{}])[0]
    response = result.get("response", {})
    res = response.get("result", {})
    cols = [c["name"] for c in res.get("cols", [])]
    rows_raw = res.get("rows", [])

    rows = []
    for row in rows_raw:
        rows.append(dict(zip(cols, [cell.get("value") for cell in row])))
    return rows


# --- Local SQLite helpers ---

def _get_local_conn() -> sqlite3.Connection:
    _cfg.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_cfg.DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _local_fetchall(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    conn = _get_local_conn()
    cur = conn.execute(sql, params)
    cols = [d[0] for d in cur.description]
    result = [dict(zip(cols, row)) for row in cur.fetchall()]
    conn.close()
    return result


def _local_execute(sql: str, params: tuple = ()) -> None:
    conn = _get_local_conn()
    conn.execute(sql, params)
    conn.commit()
    conn.close()


# --- Unified interface ---

def _execute(sql: str, params: tuple = ()) -> None:
    if _USE_TURSO:
        _turso_execute(sql, params)
    else:
        _local_execute(sql, params)


def _query(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    if _USE_TURSO:
        return _turso_execute(sql, params)
    return _local_fetchall(sql, params)


_CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS opportunities (
        source_id TEXT PRIMARY KEY,
        source TEXT NOT NULL,
        title TEXT,
        solicitation_number TEXT,
        notice_type TEXT,
        agency TEXT,
        posted_date TEXT,
        response_deadline TEXT,
        url TEXT,
        description TEXT,
        contact_name TEXT,
        contact_email TEXT,
        contact_phone TEXT,
        place_of_performance TEXT,
        office TEXT,
        naics_code TEXT,
        set_aside TEXT,
        fit_score INTEGER DEFAULT 0,
        recommended_action TEXT DEFAULT 'pending',
        stage1_json TEXT,
        stage2_json TEXT,
        raw_json TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        notion_page_id TEXT,
        notified_slack INTEGER DEFAULT 0,
        pipeline_status TEXT DEFAULT 'new',
        pipeline_notes TEXT,
        pipeline_updated_at TEXT,
        assigned_to TEXT
    )
"""


def init_db() -> None:
    _execute(_CREATE_TABLE_SQL)


def is_seen(source_id: str) -> bool:
    rows = _query("SELECT 1 FROM opportunities WHERE source_id = ?", (source_id,))
    return len(rows) > 0


def upsert_opportunity(opp: dict[str, Any]) -> None:
    poc = opp.get("point_of_contact") or {}
    _execute(
        """
        INSERT INTO opportunities (
            source_id, source, title, solicitation_number, notice_type,
            agency, posted_date, response_deadline, url,
            description, contact_name, contact_email, contact_phone,
            place_of_performance, office, naics_code, set_aside,
            fit_score, recommended_action, stage1_json, stage2_json, raw_json,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source_id) DO UPDATE SET
            fit_score = excluded.fit_score,
            recommended_action = excluded.recommended_action,
            stage1_json = excluded.stage1_json,
            stage2_json = excluded.stage2_json,
            updated_at = excluded.updated_at
        """,
        (
            opp.get("source_id", ""),
            opp.get("source", ""),
            opp.get("title", ""),
            opp.get("solicitation_number", ""),
            opp.get("notice_type", ""),
            opp.get("agency", ""),
            opp.get("posted_date"),
            opp.get("response_deadline"),
            opp.get("url", ""),
            opp.get("description", ""),
            poc.get("name", ""),
            poc.get("email", ""),
            poc.get("phone", ""),
            opp.get("place_of_performance", ""),
            opp.get("office", ""),
            opp.get("naics_code", ""),
            opp.get("set_aside", ""),
            opp.get("fit_score", 0),
            opp.get("recommended_action", "pending"),
            json.dumps(opp.get("stage1")) if opp.get("stage1") else None,
            json.dumps(opp.get("stage2")) if opp.get("stage2") else None,
            json.dumps(opp.get("raw")) if opp.get("raw") else None,
            datetime.utcnow().isoformat(),
        ),
    )


def set_notion_page_id(source_id: str, page_id: str) -> None:
    _execute(
        "UPDATE opportunities SET notion_page_id = ? WHERE source_id = ?",
        (page_id, source_id),
    )


def set_slack_notified(source_id: str) -> None:
    _execute(
        "UPDATE opportunities SET notified_slack = 1 WHERE source_id = ?",
        (source_id,),
    )


PIPELINE_STATUSES = ["new", "in_progress", "submitted", "won", "lost", "skipped"]


def set_pipeline_status(
    source_id: str,
    status: str,
    notes: str | None = None,
    assigned_to: str | None = None,
) -> None:
    updates = ["pipeline_status = ?", "pipeline_updated_at = ?"]
    params: list[Any] = [status, datetime.utcnow().isoformat()]
    if notes is not None:
        updates.append("pipeline_notes = ?")
        params.append(notes)
    if assigned_to is not None:
        updates.append("assigned_to = ?")
        params.append(assigned_to)
    params.append(source_id)
    _execute(
        f"UPDATE opportunities SET {', '.join(updates)} WHERE source_id = ?",
        tuple(params),
    )


def get_by_pipeline_status(status: str, min_score: int = 0) -> list[dict[str, Any]]:
    return _query("""
        SELECT * FROM opportunities
        WHERE pipeline_status = ? AND fit_score >= ?
        ORDER BY fit_score DESC, response_deadline ASC
    """, (status, min_score))


def get_unnotified(min_score: int = 0) -> list[dict[str, Any]]:
    return _query("""
        SELECT * FROM opportunities
        WHERE notified_slack = 0 AND fit_score >= ?
        ORDER BY fit_score DESC
    """, (min_score,))


def get_all_scored(min_score: int = 0) -> list[dict[str, Any]]:
    return _query("""
        SELECT * FROM opportunities
        WHERE fit_score >= ?
        ORDER BY fit_score DESC, response_deadline ASC
    """, (min_score,))
