"""SQLite storage — uses Turso HTTP API (cloud) when configured, local file otherwise."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from typing import Any

import httpx

import os as _os


def _turso_url() -> str:
    url = _os.environ.get("TURSO_DATABASE_URL", "")
    if url.startswith("libsql://"):
        url = url.replace("libsql://", "https://", 1)
    return url


def _turso_auth() -> str:
    return _os.environ.get("TURSO_AUTH_TOKEN", "")


def _use_turso() -> bool:
    return bool(_os.environ.get("TURSO_DATABASE_URL") and _os.environ.get("TURSO_AUTH_TOKEN"))


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
    headers = {"Authorization": f"Bearer {_turso_auth()}"}

    resp = httpx.post(url, json=body, headers=headers, timeout=30.0)
    resp.raise_for_status()
    data = resp.json()

    result = data.get("results", [{}])[0]
    if result.get("type") == "error":
        err = result.get("error") or {}
        raise RuntimeError(f"Turso error: {err.get('message') or err} — SQL: {sql[:200]}")
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
    from oppos.config import DB_PATH
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
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
    if _use_turso():
        _turso_execute(sql, params)
    else:
        _local_execute(sql, params)


def _query(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    if _use_turso():
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
        attachment_text TEXT,
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

_CREATE_META_SQL = """
    CREATE TABLE IF NOT EXISTS meta (
        key TEXT PRIMARY KEY,
        value TEXT
    )
"""

_CREATE_HEALTH_SQL = """
    CREATE TABLE IF NOT EXISTS source_health (
        source TEXT PRIMARY KEY,
        display_name TEXT,
        last_run TEXT,
        last_success TEXT,
        last_error TEXT,
        last_count INTEGER DEFAULT 0,
        last_new INTEGER DEFAULT 0,
        duration_s REAL DEFAULT 0,
        consecutive_failures INTEGER DEFAULT 0
    )
"""

_CREATE_PURSUITS_SQL = """
    CREATE TABLE IF NOT EXISTS pursuits (
        source_id TEXT PRIMARY KEY,
        owner_email TEXT,
        owner_name TEXT,
        lob TEXT,
        reason TEXT,
        status TEXT DEFAULT 'active',
        qa_deadline TEXT,
        submission_deadline TEXT,
        submission_method TEXT DEFAULT 'unknown',
        portal TEXT,
        registration_status TEXT DEFAULT 'unknown',
        checklist_json TEXT,
        next_action TEXT,
        notion_page_id TEXT,
        slack_channel_id TEXT,
        slack_channel_name TEXT,
        created_by TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        closed_at TEXT
    )
"""

_CREATE_PURSUIT_EVENTS_SQL = """
    CREATE TABLE IF NOT EXISTS pursuit_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_id TEXT NOT NULL,
        ts TEXT DEFAULT CURRENT_TIMESTAMP,
        actor TEXT,
        kind TEXT,
        detail TEXT
    )
"""

_CREATE_REGISTRATIONS_SQL = """
    CREATE TABLE IF NOT EXISTS portal_registrations (
        portal TEXT PRIMARY KEY,
        display_name TEXT,
        status TEXT DEFAULT 'unknown',
        vendor_id TEXT,
        login_owner TEXT,
        lead_time_days INTEGER,
        url TEXT,
        notes TEXT,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
"""

_CREATE_REMINDERS_SQL = """
    CREATE TABLE IF NOT EXISTS reminders_sent (
        source_id TEXT NOT NULL,
        kind TEXT NOT NULL,
        sent_at TEXT DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (source_id, kind)
    )
"""

_MIGRATIONS = [
    "ALTER TABLE opportunities ADD COLUMN attachment_text TEXT",
    "ALTER TABLE opportunities ADD COLUMN lob TEXT",
    "ALTER TABLE opportunities ADD COLUMN submitted_by TEXT",
]


def init_db() -> None:
    _execute(_CREATE_TABLE_SQL)
    _execute(_CREATE_META_SQL)
    _execute(_CREATE_HEALTH_SQL)
    _execute(_CREATE_PURSUITS_SQL)
    _execute(_CREATE_PURSUIT_EVENTS_SQL)
    _execute(_CREATE_REGISTRATIONS_SQL)
    _execute(_CREATE_REMINDERS_SQL)
    for migration in _MIGRATIONS:
        try:
            _execute(migration)
        except Exception:
            pass


def set_meta(key: str, value: str) -> None:
    """Upsert a key-value pair in the meta table."""
    _execute(
        "INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def get_meta(key: str) -> str | None:
    """Get a value from the meta table."""
    rows = _query("SELECT value FROM meta WHERE key = ?", (key,))
    return rows[0]["value"] if rows else None


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
            attachment_text, lob, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source_id) DO UPDATE SET
            fit_score = excluded.fit_score,
            recommended_action = excluded.recommended_action,
            stage1_json = excluded.stage1_json,
            stage2_json = excluded.stage2_json,
            attachment_text = COALESCE(excluded.attachment_text, attachment_text),
            lob = COALESCE(excluded.lob, lob),
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
            opp.get("attachment_text"),
            opp.get("lob"),
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


PIPELINE_STATUSES = [
    "new", "qualified", "expiring_soon", "in_progress",
    "submitted", "won", "lost", "skipped", "expired",
]


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


# ---------------------------------------------------------------------------
# Deadline-based status transitions
# ---------------------------------------------------------------------------

# Statuses that should be checked for deadline expiration.
# Once an RFP is won/lost/skipped it stays there regardless of deadline.
_DEADLINE_CHECK_STATUSES = ("new", "qualified", "expiring_soon", "in_progress")

_DEADLINE_FORMATS = [
    "%Y-%m-%dT%H:%M:%S",       # ISO with time
    "%Y-%m-%dT%H:%M:%S.%f",    # ISO with microseconds
    "%Y-%m-%dT%H:%M:%S%z",     # ISO with timezone
    "%Y-%m-%d %H:%M:%S",       # space-separated
    "%Y-%m-%d",                 # date only (treat as end of day)
    "%m/%d/%Y %I:%M %p",       # US format with time
    "%m/%d/%Y",                 # US date only
    "%b %d, %Y %I:%M %p",      # "Jan 15, 2026 2:00 PM"
    "%b %d, %Y",                # "Jan 15, 2026"
    "%B %d, %Y",                # "January 15, 2026"
]


def _parse_deadline(raw: str | None) -> datetime | None:
    """Parse a response_deadline string into a datetime. Returns None if unparseable."""
    if not raw:
        return None
    raw = raw.strip()
    for fmt in _DEADLINE_FORMATS:
        try:
            dt = datetime.strptime(raw, fmt)
            # If date-only format (no time component), assume end of business day
            if fmt in ("%Y-%m-%d", "%m/%d/%Y", "%b %d, %Y", "%B %d, %Y"):
                dt = dt.replace(hour=17, minute=0, second=0)
            return dt
        except ValueError:
            continue
    return None


def check_deadlines(warn_days: int = 7) -> dict[str, int]:
    """Check all active opportunities and move them to expiring_soon / expired.

    - expired: deadline has passed (date + time)
    - expiring_soon: deadline is within `warn_days` days

    Returns {"expired": n, "expiring_soon": n} counts of transitions made.
    """
    now = datetime.utcnow()
    warn_cutoff = now + timedelta(days=warn_days)

    placeholders = ", ".join("?" for _ in _DEADLINE_CHECK_STATUSES)
    rows = _query(
        f"""SELECT source_id, response_deadline, pipeline_status
            FROM opportunities
            WHERE pipeline_status IN ({placeholders})
              AND response_deadline IS NOT NULL
              AND response_deadline != ''""",
        tuple(_DEADLINE_CHECK_STATUSES),
    )

    counts = {"expired": 0, "expiring_soon": 0}

    for row in rows:
        dl = _parse_deadline(row.get("response_deadline"))
        if dl is None:
            continue
        # Normalize to naive UTC for comparison
        if dl.tzinfo is not None:
            dl = dl.replace(tzinfo=None)

        current_status = row.get("pipeline_status") or "new"
        sid = row["source_id"]

        if dl <= now:
            # Deadline has passed — mark expired
            if current_status != "expired":
                set_pipeline_status(sid, "expired", notes="Auto-expired — deadline passed")
                counts["expired"] += 1
        elif dl <= warn_cutoff:
            # Within warning window — mark expiring soon
            # Don't downgrade in_progress to expiring_soon; they're already being worked
            if current_status in ("new", "qualified", "expiring_soon"):
                if current_status != "expiring_soon":
                    set_pipeline_status(sid, "expiring_soon", notes=f"Deadline within {warn_days} days")
                    counts["expiring_soon"] += 1

    return counts


# ---------------------------------------------------------------------------
# Source health — one row per source, updated on every scan
# ---------------------------------------------------------------------------

def record_source_health(
    source: str,
    display_name: str,
    ok: bool,
    count: int = 0,
    new: int = 0,
    error: str | None = None,
    duration_s: float = 0.0,
) -> None:
    now = datetime.utcnow().isoformat()
    err = (error or "")[:500] if not ok else None
    _execute(
        """
        INSERT INTO source_health (
            source, display_name, last_run, last_success, last_error,
            last_count, last_new, duration_s, consecutive_failures
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source) DO UPDATE SET
            display_name = excluded.display_name,
            last_run = excluded.last_run,
            last_success = COALESCE(excluded.last_success, last_success),
            last_error = excluded.last_error,
            last_count = excluded.last_count,
            last_new = excluded.last_new,
            duration_s = excluded.duration_s,
            consecutive_failures = CASE WHEN excluded.last_error IS NULL THEN 0
                                        ELSE consecutive_failures + 1 END
        """,
        (
            source, display_name, now, now if ok else None, err,
            int(count), int(new), round(float(duration_s), 1), 0 if ok else 1,
        ),
    )


def get_source_health() -> list[dict[str, Any]]:
    """All sources with health rows, failing first, then by display name."""
    return _query(
        """SELECT * FROM source_health
           ORDER BY (last_error IS NOT NULL) DESC, display_name ASC"""
    )


def get_lob_counts(statuses: tuple[str, ...] = ("new", "qualified", "expiring_soon")) -> dict[str, int]:
    """Count of active opportunities per LOB (NULL lob reported as 'unrouted')."""
    placeholders = ", ".join("?" for _ in statuses)
    rows = _query(
        f"""SELECT COALESCE(lob, 'unrouted') AS lob, COUNT(*) AS n
            FROM opportunities WHERE pipeline_status IN ({placeholders})
            GROUP BY COALESCE(lob, 'unrouted')""",
        tuple(statuses),
    )
    return {r["lob"]: int(r["n"]) for r in rows}


# ---------------------------------------------------------------------------
# Pursuits
# ---------------------------------------------------------------------------

_PURSUIT_FIELDS = (
    "owner_email", "owner_name", "lob", "reason", "status", "qa_deadline", "submission_deadline",
    "submission_method", "portal", "registration_status", "checklist_json", "next_action",
    "notion_page_id", "slack_channel_id", "slack_channel_name", "created_by", "closed_at",
)


def create_pursuit(source_id: str, **fields: Any) -> None:
    cols = ["source_id"] + [k for k in fields if k in _PURSUIT_FIELDS]
    vals: list[Any] = [source_id] + [fields[k] for k in cols[1:]]
    placeholders = ", ".join("?" for _ in cols)
    _execute(
        f"INSERT INTO pursuits ({', '.join(cols)}) VALUES ({placeholders}) "
        f"ON CONFLICT(source_id) DO UPDATE SET " +
        ", ".join(f"{c} = excluded.{c}" for c in cols[1:]) + ", updated_at = CURRENT_TIMESTAMP",
        tuple(vals),
    )


def update_pursuit(source_id: str, **fields: Any) -> None:
    sets = [f"{k} = ?" for k in fields if k in _PURSUIT_FIELDS]
    if not sets:
        return
    params: list[Any] = [fields[k] for k in fields if k in _PURSUIT_FIELDS]
    params.append(source_id)
    _execute(
        f"UPDATE pursuits SET {', '.join(sets)}, updated_at = CURRENT_TIMESTAMP WHERE source_id = ?",
        tuple(params),
    )


def get_pursuit(source_id: str) -> dict[str, Any] | None:
    rows = _query("SELECT * FROM pursuits WHERE source_id = ?", (source_id,))
    return rows[0] if rows else None


def list_pursuits(status: str | tuple[str, ...] | None = "active", owner_email: str | None = None) -> list[dict[str, Any]]:
    where, params = [], []
    if status:
        statuses = (status,) if isinstance(status, str) else tuple(status)
        where.append(f"status IN ({', '.join('?' for _ in statuses)})"); params.extend(statuses)
    if owner_email:
        where.append("LOWER(owner_email) = ?"); params.append(owner_email.lower())
    sql = "SELECT * FROM pursuits"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY COALESCE(submission_deadline, '9999') ASC, created_at DESC"
    return _query(sql, tuple(params))


def add_pursuit_event(source_id: str, actor: str, kind: str, detail: str = "") -> None:
    _execute(
        "INSERT INTO pursuit_events (source_id, ts, actor, kind, detail) VALUES (?, ?, ?, ?, ?)",
        (source_id, datetime.utcnow().isoformat(), actor or "", kind, (detail or "")[:1000]),
    )


def get_pursuit_events(source_id: str, limit: int = 50) -> list[dict[str, Any]]:
    return _query(
        "SELECT * FROM pursuit_events WHERE source_id = ? ORDER BY ts DESC LIMIT ?",
        (source_id, int(limit)),
    )


def last_pursuit_activity(source_id: str) -> str | None:
    rows = _query("SELECT MAX(ts) AS ts FROM pursuit_events WHERE source_id = ?", (source_id,))
    return rows[0]["ts"] if rows and rows[0].get("ts") else None


def get_opps_by_ids(source_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not source_ids:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for i in range(0, len(source_ids), 100):  # keep statements small for the HTTP API
        chunk = source_ids[i:i + 100]
        placeholders = ", ".join("?" for _ in chunk)
        for r in _query(f"SELECT * FROM opportunities WHERE source_id IN ({placeholders})", tuple(chunk)):
            out[r["source_id"]] = r
    return out


# ---------------------------------------------------------------------------
# Portal registrations
# ---------------------------------------------------------------------------

_REG_FIELDS = ("display_name", "status", "vendor_id", "login_owner", "lead_time_days", "url", "notes")


def list_portal_registrations() -> list[dict[str, Any]]:
    return _query("SELECT * FROM portal_registrations ORDER BY display_name ASC")


def get_portal_registration(portal: str) -> dict[str, Any] | None:
    rows = _query("SELECT * FROM portal_registrations WHERE portal = ?", (portal,))
    return rows[0] if rows else None


def upsert_portal_registration(portal: str, **fields: Any) -> None:
    cols = ["portal"] + [k for k in fields if k in _REG_FIELDS]
    vals: list[Any] = [portal] + [fields[k] for k in cols[1:]]
    _execute(
        f"INSERT INTO portal_registrations ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)}) "
        f"ON CONFLICT(portal) DO UPDATE SET " +
        ", ".join(f"{c} = excluded.{c}" for c in cols[1:]) + ", updated_at = CURRENT_TIMESTAMP",
        tuple(vals),
    )


def seed_portal_registrations(sources: list[tuple[str, str]]) -> int:
    """Insert an 'unknown' row for every source that has none. Returns rows added."""
    existing = {r["portal"] for r in list_portal_registrations()}
    added = 0
    for key, name in sources:
        if key not in existing:
            _execute(
                "INSERT OR IGNORE INTO portal_registrations (portal, display_name, status) VALUES (?, ?, 'unknown')",
                (key, name),
            )
            added += 1
    return added


# ---------------------------------------------------------------------------
# Reminders
# ---------------------------------------------------------------------------

def reminder_sent(source_id: str, kind: str) -> bool:
    return bool(_query("SELECT 1 FROM reminders_sent WHERE source_id = ? AND kind = ?", (source_id, kind)))


def mark_reminder_sent(source_id: str, kind: str) -> None:
    _execute(
        "INSERT OR IGNORE INTO reminders_sent (source_id, kind, sent_at) VALUES (?, ?, ?)",
        (source_id, kind, datetime.utcnow().isoformat()),
    )


def set_submitted_by(source_id: str, email: str) -> None:
    _execute("UPDATE opportunities SET submitted_by = ? WHERE source_id = ?", (email, source_id))


# ---------------------------------------------------------------------------
# Settings: excluded sources
# ---------------------------------------------------------------------------

_EXCLUDED_KEY = "excluded_sources"


def get_excluded_sources() -> list[str]:
    raw = get_meta(_EXCLUDED_KEY)
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return sorted({str(x) for x in data if x})


def set_excluded_sources(sources: list[str]) -> None:
    set_meta(_EXCLUDED_KEY, json.dumps(sorted({s for s in sources if s})))


def list_sources_in_db() -> list[tuple[str, int]]:
    """Distinct source keys present in opportunities with their row counts."""
    rows = _query("SELECT source, COUNT(*) AS n FROM opportunities GROUP BY source ORDER BY n DESC")
    return [(r["source"], int(r["n"])) for r in rows if r.get("source")]


def count_active_by_sources(sources: list[str]) -> int:
    if not sources:
        return 0
    ph = ", ".join("?" for _ in sources)
    rows = _query(
        f"""SELECT COUNT(*) AS n FROM opportunities
            WHERE source IN ({ph}) AND pipeline_status IN ('new', 'qualified', 'expiring_soon')
              AND source_id NOT IN (SELECT source_id FROM pursuits WHERE status IN ('evaluating', 'active'))""",
        tuple(sources),
    )
    return int(rows[0]["n"]) if rows else 0


def archive_sources(sources: list[str], note: str = "Source excluded") -> int:
    """Move every still-active, unclaimed row from these sources to skipped. Returns rows changed.

    Opportunities with an open pursuit (claimed or pursuing) are left alone — the
    owner is working them regardless of where they were found.
    """
    if not sources:
        return 0
    n = count_active_by_sources(sources)
    ph = ", ".join("?" for _ in sources)
    _execute(
        f"""UPDATE opportunities
            SET pipeline_status = 'skipped', pipeline_notes = ?, pipeline_updated_at = ?
            WHERE source IN ({ph}) AND pipeline_status IN ('new', 'qualified', 'expiring_soon')
              AND source_id NOT IN (SELECT source_id FROM pursuits WHERE status IN ('evaluating', 'active'))""",
        (note, datetime.utcnow().isoformat(), *sources),
    )
    return n
