"""OppOS Streamlit dashboard.

Run with:
    streamlit run oppos/dashboard/app.py
"""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import os

_secrets_loaded = []
_secrets_errors = []
_secrets_keys = []
try:
    if hasattr(st, "secrets"):
        _secrets_keys = list(st.secrets)
except Exception as e:
    _secrets_errors.append(f"listing secrets: {e}")

for key in ("TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN", "SAM_GOV_API_KEY", "ANTHROPIC_API_KEY", "SLACK_WEBHOOK_URL", "NUTRIENT_API_KEY", "NOTION_TOKEN", "NOTION_DATABASE_ID"):
    try:
        if hasattr(st, "secrets") and key in st.secrets:
            val = str(st.secrets[key]).strip().strip('"').strip("'")
            if val:
                os.environ[key] = val
                _secrets_loaded.append(key)
    except Exception as e:
        _secrets_errors.append(f"{key}: {e}")

from oppos.auth import auth_configured, can_work, logout_button, member_emails, require_login
from oppos.scoring.schema import lob_label, point_claim, point_evidence, points_text
from oppos.pursuits import registration_badge as _reg_badge
from oppos.config import DB_PATH, DOCAUTH_LICENSE_KEY, PORTAL_ACCESS_REQUEST_URL, SOURCE_STATE_MAP, VIEWER_LICENSE_KEY


def _secret(name: str, env_value: str) -> str:
    """A setting from the environment, else from Streamlit secrets (Community Cloud keeps secrets.toml entries there)."""
    if env_value:
        return env_value
    try:
        return str(st.secrets.get(name, "") or "")
    except Exception:  # no secrets file locally
        return ""


DOCAUTH_LICENSE_KEY = _secret("DOCAUTH_LICENSE_KEY", DOCAUTH_LICENSE_KEY)
VIEWER_LICENSE_KEY = _secret("VIEWER_LICENSE_KEY", VIEWER_LICENSE_KEY)
from oppos.sources.registry import list_available
from oppos.storage.db import check_deadlines, get_all_scored, get_by_pipeline_status, get_meta, init_db, set_meta, set_pipeline_status

ATTACHMENTS_DIR = DB_PATH.parent / "attachments"


def _att_dir(source_id: str) -> Path:
    """The attachment folder for an opportunity — the same sanitised name the downloader writes to."""
    from oppos.sources.attachments import _sanitize_filename
    return ATTACHMENTS_DIR / _sanitize_filename(str(source_id or ""))

NUTRIENT_ICON_SVG = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 50 36'%3E%3Cpath d='M4.15 22.15C1.86 22.15 0 20.29 0 18s1.86-4.15 4.15-4.15 4.15 1.86 4.15 4.15-1.86 4.15-4.15 4.15zm41.52-8.3c-2.29 0-4.15 1.86-4.15 4.15s1.86 4.15 4.15 4.15 4.15-1.86 4.15-4.15-1.86-4.15-4.15-4.15zM6.34 28.16c-1.76 1.47-1.99 4.09-.51 5.85s4.09 1.99 5.85.51 1.99-4.09.51-5.85-4.09-1.99-5.85-.51zm37.15-20.33c1.76-1.47 1.99-4.09.51-5.85s-4.09-1.99-5.85-.51-1.99 4.09-.51 5.85 4.09 1.99 5.85.51zM11.68 1.47C9.92 0 7.3.23 5.83 1.99s-.23 4.38 1.51 5.85 4.38.23 5.85-1.51.23-4.38-1.51-5.85zm31.81 26.69c-1.76-1.47-4.38-1.25-5.85.51s-1.25 4.38.51 5.85 4.38 1.25 5.85-.51 1.25-4.38-.51-5.85zm-10.6-8.9c-1.76-1.47-4.38-1.25-5.85.51s-1.25 4.38.51 5.85 4.38 1.25 5.85-.51 1.25-4.38-.51-5.85zm-10.6-8.9c-1.76-1.47-4.38-1.25-5.85.51s-1.25 4.38.51 5.85 4.38 1.25 5.85-.51 1.25-4.38-.51-5.85z' fill='%23f0c966'/%3E%3C/svg%3E"

st.set_page_config(page_title="OppOS — Nutrient", page_icon=NUTRIENT_ICON_SVG, layout="wide")

NUTRIENT_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700&display=swap');

/* One accent (the next step), one warning colour (time pressure and unknowns that block a submission), greys
   for everything else. Archivo matches the response documents. */
:root {
    --bg: #171413; --surface: #201c1a; --raised: #2a2522; --line: #3a3330;
    --text: #efe9e3; --muted: #a39a92; --faint: #6f6761;
    --accent: #f0c966; --alert: #e2a65a;
    /* older names still used by inline styles */
    --text-primary: var(--text); --text-secondary: var(--muted); --text-tertiary: var(--faint);
    --accent-gold: var(--accent); --border-subtle: var(--line); --border-medium: var(--line);
    --radius-sm: 7px;
}
.stApp { background: var(--bg); }
.stApp, .stApp :is(p, li, label, button, input, textarea, h1, h2, h3, h4, a, td, th, div, code) { font-family: 'Archivo', system-ui, sans-serif; }
.stApp code { font-family: ui-monospace, Menlo, monospace; font-size: .9em; }

/* Streamlit chrome: keep the header (it hosts the navigation), hide the rest; no grey fade on reruns */
#MainMenu, footer { visibility: hidden; }
.stApp [data-stale="true"], .element-container[data-stale="true"], [data-stale="true"] { opacity: 1 !important; transition: none !important; }
[data-testid="stStatusWidget"] { visibility: hidden !important; }
.stDeployButton, [data-testid="stAppDeployButton"], [data-testid="stToolbarActions"] { display: none; }
header[data-testid="stHeader"] { background: var(--bg); }
.block-container { padding-top: 4.25rem !important; max-width: 1240px !important; }

/* Header */
.oppos-header { display: flex; align-items: center; }
.oppos-header-left { display: flex; align-items: center; gap: 10px; }
.oppos-header h1 { font-size: 22px !important; font-weight: 700; margin: 0; padding: 0 !important; letter-spacing: -.01em; }
.nutrient-logo-mark svg { width: 26px; height: 19px; display: block; }
.who { font-size: 13px; color: var(--faint); text-align: right; }
.welcome { font-size: 15px; line-height: 1.55; color: var(--muted); }
.welcome-title { font-size: 17px; font-weight: 600; color: var(--text); margin-bottom: 6px; }
.welcome-step b { color: var(--text); font-weight: 600; margin-right: 4px; }

/* Text helpers */
.muted { color: var(--muted); font-size: 14px; margin: 0 0 8px; }
.faint { color: var(--faint); }
.alert { color: var(--alert); }
.summary { color: var(--muted); font-size: 14.5px; line-height: 1.55; max-width: 80ch; margin: 6px 0 12px; }
.rs-head { font-size: 14.5px; font-weight: 600; color: var(--text); margin: 6px 0 6px; }
ul.plain { margin: 0 0 10px; padding-left: 18px; color: var(--muted); font-size: 14px; }
ul.plain li { margin-bottom: 4px; }
.evidence-quote { color: var(--faint); font-size: 13px; margin: 2px 0 4px; }
.kvs { margin: 14px 0 6px; }
.kv { display: grid; grid-template-columns: 150px minmax(0, 1fr); gap: 14px; font-size: 14px; padding: 4px 0; color: var(--text); }
.kv > span { color: var(--muted); }
.kv a, .ws-links a, .fact a, a.quiet-link { color: var(--accent); text-decoration: none; }
.empty-state { padding: 36px 0; color: var(--muted); }
.empty-state h3 { font-size: 16px !important; font-weight: 500; color: var(--muted); }

/* Buttons, tabs, inputs */
.stButton > button, [data-testid="stPopover"] > button, [data-testid="stDownloadButton"] > button, [data-testid="stLinkButton"] > a {
    font-size: 14px; font-weight: 500; min-height: 36px; padding: 4px 14px; border-radius: var(--radius-sm); }
.stButton > button[kind="primary"], [data-testid="stPopover"] > button[kind="primary"] { color: #1d1708; font-weight: 600; }
.stButton > button[kind="primary"]:disabled { background: var(--raised); border-color: var(--line); color: var(--faint); }
[data-testid="stTabs"] [data-baseweb="tab"] { font-size: 14.5px; }
[data-testid="stTabs"] [data-baseweb="tab-highlight"] { background: var(--text); }
[data-testid="stExpander"] details { border: 1px solid var(--line); border-radius: var(--radius-sm); }
[data-testid="stExpander"] summary { font-size: 14px; color: var(--muted); }
[data-testid="stCaptionContainer"] { font-size: 13px; }
[data-testid="stDownloadButton"] > button[kind="tertiary"], .stButton > button[kind="tertiary"] { color: var(--accent); }
[data-testid="stDownloadButton"] > button[kind="tertiary"] { min-height: 0; padding: 0; }
[class*="_docs_head"] { margin-bottom: 6px; }
[class*="_docs_head"] [data-testid="stDownloadButton"] { margin-left: auto; }

/* Find RFPs rows */
[class*="st-key-row_"] { border-bottom: 1px solid var(--line); padding: 8px 0; }
[class*="st-key-row_"] .stButton > button[kind="tertiary"] { padding: 0; min-height: 0; font-size: 16px; font-weight: 600; color: var(--text); text-align: left; justify-content: flex-start; }
[class*="st-key-row_"] .stButton > button[kind="tertiary"]:hover { color: var(--accent); }
.score { font-size: 20px; font-weight: 700; text-align: center; color: var(--text); }
.score.low { color: var(--muted); }
.rmeta { color: var(--muted); font-size: 13.5px; margin-top: -4px; }
.rwhy { color: var(--muted); font-size: 13.5px; margin-top: 3px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 88ch; }

/* My desk rail: the radio list reads as a list of pursuits */
.st-key-desk_rail [role="radiogroup"] { gap: 2px; }
.st-key-desk_rail [role="radiogroup"] > label { padding: 9px 12px; border-left: 3px solid transparent; border-radius: 0 6px 6px 0; width: 100%; margin: 0; }
.st-key-desk_rail [role="radiogroup"] > label:has(input:checked) { background: var(--raised); border-left-color: var(--accent); }
.st-key-desk_rail [role="radiogroup"] > label > div:first-child { display: none; }
.st-key-desk_rail [role="radiogroup"] p { font-size: 14px; font-weight: 500; line-height: 1.3; }
.st-key-desk_rail [data-testid="stCaptionContainer"] { font-size: 12.5px; color: var(--muted); }
.closed-row { font-size: 13.5px; color: var(--muted); padding-top: 6px; }
.closed-row span { display: block; color: var(--faint); font-size: 12.5px; }

/* Pursuit workspace */
.ws-head { display: flex; justify-content: space-between; gap: 20px; margin-bottom: 6px; }
.ws-title { font-size: 22px; font-weight: 700; line-height: 1.25; letter-spacing: -.01em; }
.ws-title a { color: var(--text); text-decoration: none; }
.ws-title a:hover { color: var(--accent); }
.ws-sub { color: var(--muted); font-size: 14px; margin-top: 4px; }
.ws-links { font-size: 13.5px; margin-top: 4px; }
.ws-links a + a { margin-left: 14px; }
.ws-fit { text-align: right; flex: none; }
.ws-fit b { display: block; font-size: 26px; font-weight: 700; line-height: 1; }
.ws-fit span { font-size: 12px; color: var(--muted); }
.journey { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; font-size: 14px; }
.journey i { width: 22px; height: 1px; background: var(--line); }
.journey .step { color: var(--faint); }
.journey .step.done { color: var(--muted); }
.journey .step.now { color: var(--text); font-weight: 600; }
[class*="st-key-facts_"] { background: var(--surface); border-radius: 8px; padding: 14px 18px; margin: 10px 0 4px; gap: 6px !important; }
.fact { display: grid; grid-template-columns: 110px minmax(0, 1fr); gap: 14px; font-size: 14.5px; padding: 3px 0; }
.fact > span, .fact-label { color: var(--muted); font-size: 14.5px; }
.fact .help, .help { color: var(--faint); font-size: 13px; margin-top: 2px; line-height: 1.45; }
.fact .unknown { color: var(--muted); }
.next-help { color: var(--faint); font-size: 13px; text-align: right; margin: -6px 0 6px; }
.collab { background: var(--surface); border-radius: 8px; padding: 12px 16px; margin: 8px 0; font-size: 14.5px; }
.collab .help { margin-top: 4px; }
[class*="st-key-facts_"] [data-testid="stElementContainer"] { margin: 0; }
[class*="st-key-acct_"] { margin: 2px 0; }
[class*="st-key-acct_"] [data-testid="stVerticalBlock"] { gap: 0 !important; }
[class*="st-key-acct_"] [data-testid="stPopover"] { margin-left: 12px; }
[class*="st-key-acct_"] .fact-label { padding-top: 6px; width: 110px; }
.doc-reading { color: var(--muted); font-size: 14px; padding: 4px 0 8px; }
.doc { display: grid; grid-template-columns: 44px minmax(0, 1fr) auto; gap: 12px; align-items: center; font-size: 14.5px; }
.doc .ext { font-size: 11px; font-weight: 600; color: var(--muted); border: 1px solid var(--line); border-radius: 4px; text-align: center; padding: 1px 0; }
.doc .dmeta { color: var(--faint); font-size: 13px; white-space: nowrap; }
.doc2 { display: grid; grid-template-columns: 44px minmax(0, 1fr); gap: 12px; padding: 4px 0 8px; font-size: 14.5px; }
.doc2 .ext { font-size: 11px; font-weight: 600; color: var(--muted); border: 1px solid var(--line); border-radius: 4px; text-align: center; padding: 1px 0; height: fit-content; margin-top: 2px; }
.doc2 .dmeta { color: var(--faint); font-size: 13px; margin-top: 1px; }
.doc2 .dsum { color: var(--muted); font-size: 13.5px; margin-top: 3px; line-height: 1.45; max-width: 80ch; }
.reasons { display: grid; grid-template-columns: 1fr 1fr; gap: 28px; margin: 12px 0 4px; font-size: 14px; }
.reasons ul { margin: 0; padding-left: 18px; color: var(--muted); }
.reasons li { margin-bottom: 5px; }
.draftline { margin: 0; font-size: 14.5px; color: var(--muted); }
.draftline b { color: var(--text); }
.todo { border-top: 1px solid var(--line); margin: 12px 0; }
.todo-row { display: grid; grid-template-columns: 52px minmax(0, 1fr); gap: 12px; padding: 10px 0; border-bottom: 1px solid var(--line); font-size: 14.5px; }
.todo-row .tid { color: var(--faint); font-size: 13px; }
.twhy { color: var(--muted); font-size: 13.5px; margin-top: 2px; }
.ans-head { margin-top: 16px; font-weight: 600; font-size: 14px; }
.ans-head span { margin-left: 10px; color: var(--faint); font-weight: 400; font-size: 13px; }
.ans-req { color: var(--muted); font-size: 13.5px; margin: 2px 0 6px; }
.req { padding: 8px 0; border-bottom: 1px solid var(--line); font-size: 14px; max-width: 90ch; }
.req > span { display: block; color: var(--faint); font-size: 12.5px; margin-top: 2px; }
.event { font-size: 13.5px; color: var(--muted); padding: 3px 0; }
.event span { color: var(--faint); margin-right: 10px; }

/* Admin */
.health-table { width: 100%; border-collapse: collapse; font-size: 13.5px; }
.health-table th { text-align: left; color: var(--muted); font-weight: 500; padding: 6px 8px; border-bottom: 1px solid var(--line); }
.health-table td { padding: 6px 8px; border-bottom: 1px solid var(--line); color: var(--text); }
.health-note { color: var(--faint); font-size: 13px; }

@media (max-width: 760px) {
    .reasons { grid-template-columns: 1fr; }
    .fact, .kv { grid-template-columns: 1fr; gap: 2px; }
    .rwhy { white-space: normal; }
}
</style>
"""

st.markdown(NUTRIENT_CSS, unsafe_allow_html=True)

NUTRIENT_DOTS_SVG = '<svg viewBox="0 0 50 36" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M4.15 22.15C1.86 22.15 0 20.29 0 18s1.86-4.15 4.15-4.15 4.15 1.86 4.15 4.15-1.86 4.15-4.15 4.15zm41.52-8.3c-2.29 0-4.15 1.86-4.15 4.15s1.86 4.15 4.15 4.15 4.15-1.86 4.15-4.15-1.86-4.15-4.15-4.15zM6.34 28.16c-1.76 1.47-1.99 4.09-.51 5.85s4.09 1.99 5.85.51 1.99-4.09.51-5.85-4.09-1.99-5.85-.51zm37.15-20.33c1.76-1.47 1.99-4.09.51-5.85s-4.09-1.99-5.85-.51-1.99 4.09-.51 5.85 4.09 1.99 5.85.51zM11.68 1.47C9.92 0 7.3.23 5.83 1.99s-.23 4.38 1.51 5.85 4.38.23 5.85-1.51.23-4.38-1.51-5.85zm31.81 26.69c-1.76-1.47-4.38-1.25-5.85.51s-1.25 4.38.51 5.85 4.38 1.25 5.85-.51 1.25-4.38-.51-5.85zm-10.6-8.9c-1.76-1.47-4.38-1.25-5.85.51s-1.25 4.38.51 5.85 4.38 1.25 5.85-.51 1.25-4.38-.51-5.85zm-10.6-8.9c-1.76-1.47-4.38-1.25-5.85.51s-1.25 4.38.51 5.85 4.38 1.25 5.85-.51 1.25-4.38-.51-5.85z" fill="currentColor"/></svg>'

NUTRIENT_WORDMARK_SVG = '<svg viewBox="60 0 148 36" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M83.25 4h3.56v28.09h-4.1L73.1 15.2c-.52-.94-1.6-3.04-3.25-6.3h-.04c.05 1.2.1 2.51.14 3.93.04 1.42.06 2.48.06 3.18v16.08h-3.56V4h4l9.64 16.69c.48.84 1.36 2.47 2.63 4.92l.7 1.35h.04c-.05-1.07-.1-2.3-.14-3.7-.04-1.4-.06-2.52-.06-3.37V4zm21.01 19.3c0 4.18-1.72 6.27-5.17 6.27-.77 0-1.44-.07-2.02-.21-.57-.14-1.12-.45-1.63-.95-.38-.36-.65-.78-.82-1.24-.17-.46-.27-.93-.3-1.39-.03-.46-.05-1.11-.05-1.95V12.04h-3.72v11.99c0 .94.03 1.76.09 2.45.06.69.21 1.38.44 2.07.23.69.59 1.28 1.08 1.79.72.77 1.56 1.34 2.52 1.7.97.36 2.1.55 3.41.55 1.44 0 2.69-.3 3.76-.9s1.87-1.5 2.41-2.63v3h3.6V12.04h-3.6v11.26zm14.42-16.85h-3.56v5.58h-4.21v3.02h4.21v12.1c0 1.82.49 3.13 1.47 3.93s2.56 1.2 4.74 1.2c.55 0 1.1-.03 1.64-.09.54-.06.99-.13 1.34-.22l-.08-3.29c-1.01.24-1.88.35-2.6.35-.73 0-1.35-.06-1.76-.17-.41-.11-.71-.31-.9-.6-.19-.29-.28-.7-.28-1.23V15.06h5.7v-3.02h-5.7V6.45zm16.05 6.52c-1.27.76-2.1 1.7-2.48 2.82V12.04h-3.6v20.06h3.6v-9.19c0-2.1.31-3.74.94-4.92.63-1.17 1.48-1.98 2.55-2.42 1.07-.44 2.37-.66 3.9-.66.61 0 1.03.02 1.25.06l.08-3.43c-.86 0-1.41.01-1.64.04-1.79.17-3.32.63-4.6 1.39zm35.56 5.62c.3 1.19.45 2.43.45 3.7 0 .38 0 .66-.02.84h-15.22c.04 2.21.53 3.85 1.47 4.93.94 1.08 2.35 1.62 4.23 1.62 1.7 0 3.02-.37 3.96-1.1.94-.74 1.53-1.87 1.78-3.38l3.49.27c-.45 2.34-1.45 4.11-3.01 5.31-1.56 1.2-3.62 1.8-6.18 1.8-3.08 0-5.48-.98-7.21-2.94-1.63-1.83-2.45-4.37-2.45-7.62 0-1.5.21-2.89.64-4.16.42-1.27 1.05-2.37 1.89-3.3.87-.99 1.91-1.74 3.12-2.25 1.2-.51 2.53-.76 3.97-.76 1.62 0 3.13.34 4.52 1.03 1.4.69 2.5 1.67 3.31 2.95.54.86.96 1.89 1.26 3.07zm-3.27 1.62c-.01-.57-.12-1.2-.31-1.87-.2-.67-.45-1.24-.77-1.7-.51-.76-1.15-1.31-1.91-1.66-.76-.35-1.69-.52-2.79-.52-1.1 0-2.06.19-2.88.58-.82.38-1.44.92-1.84 1.59-.34.55-.58 1.14-.73 1.76-.15.63-.24 1.23-.25 1.82h11.48zm23.66-4.61c-.23-.7-.58-1.3-1.05-1.81-.73-.77-1.58-1.34-2.55-1.7-.97-.36-2.11-.55-3.43-.55-3.07 0-5.13 1.19-6.19 3.56v-3.07h-3.6v20.06h3.6V21.03c0-2.52.54-4.23 1.63-5.12 1.08-.9 2.28-1.34 3.6-1.34.74 0 1.4.07 1.96.21.56.14 1.1.45 1.61.95.38.36.66.78.83 1.25.18.47.28.94.31 1.42.03.48.05 1.14.05 1.99v11.71h3.74v-11.9c0-.95-.03-1.78-.09-2.48-.06-.7-.2-1.4-.43-2.1zm16.67-.56v-3.02h-5.7V6.45h-3.56v5.58h-4.21v3.02h4.21v12.1c0 1.82.49 3.13 1.47 3.93s2.56 1.2 4.74 1.2c.55 0 1.1-.03 1.64-.09.54-.06.99-.13 1.34-.22l-.08-3.29c-1.01.24-1.88.35-2.6.35-.73 0-1.35-.06-1.76-.17-.41-.11-.71-.31-.9-.6-.19-.29-.28-.7-.28-1.23V15.06h5.7zm-62.78 17.07h3.6V12.06h-3.6v20.06zm1.8-28.71c-1.45 0-2.63 1.18-2.63 2.63s1.18 2.63 2.63 2.63 2.63-1.18 2.63-2.63-1.18-2.63-2.63-2.63z" fill="currentColor"/></svg>'

def _score_class(score: int) -> str:
    if score >= 65:
        return "score-high"
    if score >= 40:
        return "score-mid"
    return "score-low"


def _esc(text: str) -> str:
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("{", "&#123;")
            .replace("}", "&#125;")
            )


def _flash(msg: str, icon: str = "✅") -> None:
    """Queue a confirmation for the next rerun. Every click reruns the script, so a message written just before
    st.rerun() would vanish; the queued one is shown as a toast at the top of the next frame."""
    st.session_state.setdefault("_flash", []).append((msg, icon))


def _show_flash() -> None:
    for msg, icon in st.session_state.pop("_flash", []) or []:
        st.toast(msg, icon=icon)


CURRENT_USER = require_login()

_hc1, _hc2, _hc3, _hc4 = st.columns([4, 2.6, 1.25, 0.9], vertical_alignment="center")
_role = " · Admin" if CURRENT_USER.get("is_admin") else ""
_mode = "" if CURRENT_USER.get("authenticated") else " · local dev mode"
_hc1.markdown(f'<div class="oppos-header"><div class="oppos-header-left">'
              f'<div class="nutrient-logo-mark" style="color: var(--accent-gold);">{NUTRIENT_DOTS_SVG}</div><h1>OppOS</h1></div></div>',
              unsafe_allow_html=True)
_hc2.markdown(f'<div class="who">{_esc(CURRENT_USER["name"])}{_role}{_mode}</div>', unsafe_allow_html=True)
with _hc3:
    if st.button("How it works", key="howitworks", use_container_width=True):
        st.session_state["show_welcome"] = True
with _hc4:
    logout_button()
_show_flash()


def _welcome(only_if_asked: bool = False) -> None:
    """Three lines, the same three verbs the buttons use. Shown on Find RFPs until the person clicks Got it;
    "How it works" in the header brings it back on any page."""
    key = f"welcome_seen:{CURRENT_USER.get('email', '')}"
    asked = st.session_state.get("show_welcome")
    if not asked and (only_if_asked or _cached_meta(key)):
        return
    with st.container(border=True):
        st.markdown(
            '<div class="welcome"><div class="welcome-title">Grab. Pursue. Submit.</div>'
            '<div class="welcome-step"><b>Grab</b> anything in Find RFPs worth a look. It moves to your desk.</div>'
            '<div class="welcome-step"><b>Pursue</b> it from your desk: Start pursuing opens Notion and Slack; Draft response writes the first draft.</div>'
            '<div class="welcome-step"><b>Submit</b> the Word or PDF on the portal or by email, mark it submitted, then record the outcome.</div>'
            '</div>', unsafe_allow_html=True)
        if st.button("Got it", key="welcome_done", type="primary"):
            set_meta(key, datetime.utcnow().isoformat())
            st.session_state["show_welcome"] = False
            st.rerun()


# ── Data access for reruns ────────────────────────────────────────────────────
# Streamlit re-runs this whole script on every click. Each Turso statement is a network round trip, so the
# reads every page needs are cached (st.cache_data) and invalidated the moment anything is written: the
# db module's _execute is wrapped so any non-SELECT clears the cache. init_db runs once per process and the
# deadline sweep at most every DEADLINE_SWEEP_MINUTES.
from oppos.storage import db as _db

DEADLINE_SWEEP_MINUTES = 10
@st.cache_resource(show_spinner=False)
def _sweep_state() -> dict:
    """Process-wide (survives reruns — module-level assignments here are re-executed on every click)."""
    return {"last": 0.0}

if not getattr(_db, "_APP_INVALIDATION_INSTALLED", False):
    _orig_execute = _db._execute

    def _execute_and_invalidate(sql: str, params: tuple = ()):
        is_write = not sql.lstrip()[:6].upper().startswith("SELECT")
        try:
            return _orig_execute(sql, params)
        finally:
            # Every attempted write drops the cached reads — including one whose response was lost, which may
            # have committed; the next rerun must re-read rather than show the pre-write state for five minutes.
            if is_write:
                st.cache_data.clear()

    _db._execute = _execute_and_invalidate
    _db._APP_INVALIDATION_INSTALLED = True


@st.cache_data(ttl=300, show_spinner=False)
def _cached_registrations() -> list[dict]:
    from oppos.storage.db import list_portal_registrations
    return list_portal_registrations()


@st.cache_data(ttl=300, show_spinner=False)
def _cached_pursuits() -> list[dict]:
    from oppos.storage.db import list_pursuits
    return list_pursuits(status=None)


@st.cache_data(ttl=300, show_spinner=False)
def _cached_collaborators() -> list[dict]:
    from oppos.storage.db import list_collaborators
    return list_collaborators()


@st.cache_data(ttl=300, show_spinner=False)
def _cached_excluded() -> list[str]:
    from oppos.storage.db import get_excluded_sources
    return list(get_excluded_sources())


@st.cache_data(ttl=300, show_spinner=False)
def _cached_all_scored() -> list[dict]:
    return _db.get_all_scored(0)


@st.cache_data(ttl=300, show_spinner=False)
def _cached_meta(key: str) -> str | None:
    return _db.get_meta(key)


def _maybe_sweep_deadlines() -> None:
    import time as _time
    state = _sweep_state()
    if _time.time() - state["last"] > DEADLINE_SWEEP_MINUTES * 60:
        state["last"] = _time.time()
        check_deadlines()


init_db()
_maybe_sweep_deadlines()
# Anyone signed in can browse; grabbing and working RFPs is limited to the member list (Admin → Settings).
CURRENT_USER["can_work"] = can_work(CURRENT_USER, _cached_meta("members"))
NO_ACCESS_NOTE = "Browse only — to grab and work RFPs, ask an admin for access."
SOURCE_LABELS = dict(list_available())
SOURCE_LABELS["manual"] = "Manual Submission"
from oppos.storage.db import seed_portal_registrations
if not st.session_state.get("regs_seeded"):
    seed_portal_registrations(list(SOURCE_LABELS.items()))
    st.session_state["regs_seeded"] = True
PORTAL_REGS = {r["portal"]: r for r in _cached_registrations()}
from oppos.pursuits import OPEN_STAGES as _OPEN_STAGES
_ALL_PURSUITS = _cached_pursuits()
OPEN_PURSUITS = {p["source_id"]: p for p in _ALL_PURSUITS if p.get("status") in _OPEN_STAGES}
EXCLUDED_SOURCES = set(_cached_excluded())
COLLABS: dict[str, list[dict]] = {}
for _c in _cached_collaborators():
    COLLABS.setdefault(_c["source_id"], []).append(_c)


def _collaborators(sid: str, status: str = "approved") -> list[dict]:
    return [c for c in COLLABS.get(sid, []) if c.get("status") == status]


def _works_on(p: dict, email: str) -> bool:
    """Owner or approved collaborator."""
    return (p.get("owner_email") or "").lower() == email or any((c.get("email") or "") == email for c in _collaborators(p["source_id"]))
# Anything with a pursuit record (open or closed) lives on a desk, never in the shared pool.
# "Released" means back to the pool, so it is not counted here.
PURSUED_IDS = {p["source_id"] for p in _ALL_PURSUITS if p.get("status") != "released"}
TRACKED_IDS = PURSUED_IDS if EXCLUDED_SOURCES else set()

# Every list view hides excluded sources, except opportunities that are or were pursued.


def _visible(rows: list[dict]) -> list[dict]:
    if not EXCLUDED_SOURCES:
        return rows
    return [r for r in rows if r.get("source") not in EXCLUDED_SOURCES or r.get("source_id") in TRACKED_IDS]


def get_all_scored(min_score: int = 0) -> list[dict]:
    rows = _cached_all_scored()
    if min_score:
        rows = [r for r in rows if _score_of(r) >= min_score]
    return _visible(rows)


def _score_of(row: dict) -> float:
    """fit_score as a number — the Turso HTTP API returns every value as a string."""
    try:
        return float(row.get("fit_score") or 0)
    except (TypeError, ValueError):
        return 0.0


def _rows_by_status(status: str, min_score: int = 0) -> list[dict]:
    """Rows in one pipeline status from the cached scored set (same ordering and min-score rule as the SQL)."""
    return [r for r in _cached_all_scored() if (r.get("pipeline_status") or "new") == status and _score_of(r) >= min_score]


def get_by_pipeline_status(status: str, min_score: int = 0) -> list[dict]:
    return _visible(_rows_by_status(status, min_score))

GOOD_FIT = 40  # Find RFPs 'Good fit' view: fit score at or above this
PIPELINE_LABELS = {
    "new": "New",
    "qualified": "Qualified",
    "expiring_soon": "Expiring Soon",
    "in_progress": "Pursuing",
    "submitted": "Submitted",
    "won": "Won",
    "lost": "Lost",
    "skipped": "Skipped",
    "expired": "Expired",
}

STATUS_OPTIONS = list(PIPELINE_LABELS.keys())
STATUS_DISPLAY = list(PIPELINE_LABELS.values())


def _run_scan() -> dict:
    """Run the shared scan loop in-process with a progress bar; return stats."""
    import logging
    from oppos.pipeline import run_scan

    logging.basicConfig(level=logging.INFO)
    progress = st.progress(0, text="Starting scan...")

    def _on_progress(idx: int, total: int, name: str) -> None:
        progress.progress(idx / max(total, 1), text=f"Scanning {name}  ({idx + 1}/{total})")

    stats = run_scan(on_progress=_on_progress)
    progress.progress(1.0, text=f"Done -- scanned {stats['sources']} sources, {stats['fetched']} listings")
    return stats


def _render_source_health(rows: list[dict]) -> str:
    import html as _html
    now = datetime.now(timezone.utc)
    out = ['<table class="health-table"><tr><th></th><th>Source</th><th>Last run</th>'
           '<th>Listings</th><th>New</th><th>Note</th></tr>']
    for r in rows:
        err = r.get("last_error") or ""
        try:
            age = now - datetime.fromisoformat(str(r.get("last_run"))).replace(tzinfo=timezone.utc)
            secs = age.total_seconds()
            ago = ("just now" if secs < 60 else f"{int(secs // 60)}m ago" if secs < 3600
                   else f"{int(secs // 3600)}h ago" if secs < 86400 else f"{age.days}d ago")
            stale = age.days >= 3
        except (ValueError, TypeError):
            ago, stale = "never", True
        count = int(r.get("last_count") or 0)
        if err:
            dot, note = "🔴", _html.escape(err[:90])
        elif stale:
            dot, note = "🟡", "No run in 3+ days"
        elif count == 0:
            dot, note = "🟡", "Returned 0 listings"
        else:
            dot, note = "🟢", ""
        name = _html.escape(str(r.get("display_name") or r.get("source") or ""))
        out.append(f"<tr><td>{dot}</td><td>{name}</td><td>{ago}</td><td>{count}</td>"
                   f"<td>{int(r.get('last_new') or 0)}</td><td class=\"health-note\">{note}</td></tr>")
    out.append("</table>")
    return "".join(out)


# --- Manual RFP submission ---
def _run_manual_url(url: str) -> dict:
    """Run URL submission and return result dict."""
    from oppos.sources.manual import submit_url
    progress_log = []

    def _on_progress(step, detail=""):
        labels = {
            "duplicate": "⚠️", "fetch": "🌐", "direct_file": "📄",
            "metadata": "🧠", "attachments": "📎", "extract_text": "🔍", "scoring": "📊",
        }
        icon = labels.get(step, "➡️")
        if detail:
            st.write(f"{icon} {detail}")
            progress_log.append(f"{icon} {detail}")

    result = submit_url(url, on_progress=_on_progress)
    result["_progress_log"] = progress_log
    return result


def _run_manual_file(file_bytes: bytes, filename: str) -> dict:
    """Run file submission and return result dict."""
    from oppos.sources.manual import submit_file
    progress_log = []

    def _on_progress(step, detail=""):
        labels = {"extract_text": "🔍", "metadata": "🧠", "scoring": "📊"}
        icon = labels.get(step, "➡️")
        if detail:
            st.write(f"{icon} {detail}")
            progress_log.append(f"{icon} {detail}")

    result = submit_file(file_bytes, filename, on_progress=_on_progress)
    result["_progress_log"] = progress_log
    return result


def _after_manual_submit(result: dict) -> None:
    """Attribute the submission to the signed-in user and claim it for them."""
    from oppos.pursuits import claim_opportunity
    from oppos.storage.db import get_opps_by_ids, set_submitted_by
    sid = result.get("source_id")
    if not sid or result.get("error"):
        return
    try:
        set_submitted_by(sid, CURRENT_USER["email"])
        opp = get_opps_by_ids([sid]).get(sid) or result
        claim_opportunity(opp, CURRENT_USER, note="Submitted manually")
    except Exception as e:  # attribution must never break the submission
        st.warning(f"Submitted, but could not auto-claim: {e}")


def _go_to_desk(sid: str) -> None:
    """Open My desk with this pursuit selected."""
    st.session_state["desk_selected_Mine"] = sid
    st.session_state["pursuit_view"] = "Mine"
    st.session_state.pop("manual_result", None)
    st.switch_page(_PAGE_DESK)


@st.dialog("Add an RFP", width="large")
def _manual_rfp_dialog() -> None:
    """Three ways in, one outcome: the RFP lands on the person's desk, grabbed for them."""
    st.caption(f"Found one the scanner missed, or sourced it yourself? Add it here. It is attributed to you and lands on your desk, grabbed.")
    how = st.segmented_control("How do you have it?", ["I have a link", "I have the document", "I'll type it in"],
                               default="I have a link", key="manual_how", label_visibility="collapsed")
    result = st.session_state.get("manual_result")

    if how == "I have a link" and not result:
        st.caption("Paste the listing page or a direct link to the RFP file. The page and its documents are read and the fit scored.")
        manual_url = st.text_input("Link", key="manual_url_input", placeholder="https://procurement.example.gov/bid/12345", label_visibility="collapsed")
        if st.button("Add from link", key="manual_url_submit", type="primary", disabled=not manual_url):
            with st.status("Reading the RFP…", expanded=True) as status:
                result = _run_manual_url(manual_url)
                status.update(label="Failed" if result.get("error") else "Added", state="error" if result.get("error") else "complete")
            _after_manual_submit(result)
            st.session_state["manual_result"] = result
            if result.get("_att_files"):
                st.session_state[f"att_files_{result.get('source_id', '')}"] = result["_att_files"]
            st.rerun(scope="fragment")

    elif how == "I have the document" and not result:
        st.caption("Upload the RFP as PDF or Word. The text is read and the fit scored.")
        uploaded = st.file_uploader("RFP document", type=["pdf", "docx"], key="manual_file_upload", label_visibility="collapsed")
        if st.button("Add from file", key="manual_file_submit", type="primary", disabled=uploaded is None):
            file_bytes = uploaded.read()
            with st.status(f"Reading {uploaded.name}…", expanded=True) as status:
                result = _run_manual_file(file_bytes, uploaded.name)
                status.update(label="Failed" if result.get("error") else "Added", state="error" if result.get("error") else "complete")
            _after_manual_submit(result)
            st.session_state["manual_result"] = result
            if result.get("_att_files"):
                st.session_state[f"att_files_{result.get('source_id', '')}"] = result["_att_files"]
            st.rerun(scope="fragment")

    elif how == "I'll type it in" and not result:
        st.caption("No link or file needed. Only the title is required; add what you know and fill in the rest from your desk later.")
        from oppos.sources.manual import submit_details
        c1, c2 = st.columns([3, 2])
        with c1:
            t_title = st.text_input("What is it?", key="manual_t_title", placeholder="RFI — Document workflow platform")
            t_agency = st.text_input("Who is asking?", key="manual_t_agency", placeholder="Agency, department, or company")
            t_url = st.text_input("Link, if there is one", key="manual_t_url", placeholder="https://")
        with c2:
            t_deadline = st.date_input("Response due", value=None, key="manual_t_deadline", format="YYYY-MM-DD")
            t_sol = st.text_input("Solicitation number", key="manual_t_sol", placeholder="Optional")
            t_contact = st.text_input("Contact", key="manual_t_contact", placeholder="Name or email, optional")
        t_desc = st.text_area("What are they asking for?", key="manual_t_desc", height=120,
                              placeholder="Paste the summary or scope from the email or call notes. Used to score the fit and to draft the response.")
        t_score = st.checkbox("Score the fit now from this description", value=True, key="manual_t_score", disabled=not t_desc.strip())
        if st.button("Add to my desk", key="manual_t_submit", type="primary", disabled=not t_title.strip()):
            contact_email = t_contact.strip() if "@" in t_contact else ""
            fields = {"title": t_title, "agency": t_agency, "url": t_url, "response_deadline": t_deadline.isoformat() if t_deadline else "",
                      "solicitation_number": t_sol, "description": t_desc,
                      "contact_name": "" if contact_email else t_contact.strip(), "contact_email": contact_email}
            with st.status("Adding…", expanded=True) as status:
                result = submit_details(fields, score=bool(t_score and t_desc.strip()), on_progress=lambda step, d="": st.write(d))
                status.update(label="Failed" if result.get("error") else "Added", state="error" if result.get("error") else "complete")
            _after_manual_submit(result)
            st.session_state["manual_result"] = result
            st.rerun(scope="fragment")

    if result:
        if result.get("error"):
            st.error(f"Could not add it: {result['error']}")
            if st.button("Try again", key="manual_retry"):
                st.session_state.pop("manual_result", None)
                st.rerun(scope="fragment")
        else:
            s2 = result.get("stage2") or {}
            fit = int(_score_of(result))
            st.success(f"**{result.get('title', 'Untitled')[:90]}** is on your desk, grabbed for you"
                       + (f" · fit {fit}/100 ({lob_label(result.get('lob')) or 'unrouted'})" if fit else " · not scored yet"))
            if s2.get("summary"):
                st.caption(s2["summary"])
            b1, b2 = st.columns(2)
            with b1:
                if st.button("Open on my desk", key="manual_open_desk", type="primary", use_container_width=True):
                    _go_to_desk(result.get("source_id", ""))
            with b2:
                if st.button("Add another", key="manual_another", use_container_width=True):
                    st.session_state.pop("manual_result", None)
                    st.rerun(scope="fragment")



def _pursue_opportunity(opp: dict, reason: str = "") -> None:
    """Full Pursue flow: Notion push → pursuit record (owner = you) → Slack channel or alert."""
    from oppos.outputs.notion_sync import push_opportunity
    from oppos.pursuits import owned_by_other, start_pursuit
    from oppos.storage.db import get_pursuit, set_notion_page_id

    sid = opp.get("source_id", "")
    title = opp.get("title", "Untitled")

    _existing = get_pursuit(sid)
    if owned_by_other(_existing, CURRENT_USER):
        st.error(f"**{title[:60]}** is owned by {_existing.get('owner_name') or _existing.get('owner_email')} "
                 f"({_existing.get('status')}). Ask them to release it before pursuing.")
        return

    with st.status(f"Pursuing: {title[:50]}…", expanded=True) as status:
        notion_url, page_id = "", None
        st.write("📤 Pushing to Notion…")
        try:
            opp["pipeline_status"] = "in_progress"
            opp["pipeline_notes"] = reason or "Qualified — pursuing"
            att_dir = _att_dir(sid)
            att_paths = sorted(att_dir.glob("*")) if att_dir.exists() else []
            page_id = push_opportunity(opp, attachment_paths=att_paths or None)
            if page_id:
                set_notion_page_id(sid, page_id)
                notion_url = f"https://notion.so/{page_id.replace('-', '')}"
                st.write(f"✓ Notion page created — [Open]({notion_url})")
            else:
                from oppos.outputs import notion_sync as _ns
                st.write(f"⚠️ Notion push failed — continuing. Notion said: {_ns.LAST_ERROR or 'no reason returned'}")
        except Exception as e:
            st.write(f"⚠️ Notion error: {e} — continuing…")

        st.write("📋 Creating pursuit record…")
        result = start_pursuit(opp, reason=reason, user=CURRENT_USER, notion_url=notion_url, notion_page_id=page_id)
        if result.get("slack_channel_name"):
            st.write(f"✓ Slack channel [#{result['slack_channel_name']}]({result['slack_url']}) created and brief pinned")
        elif result.get("slack_alert_sent"):
            st.write("✓ Slack alert sent (set SLACK_BOT_TOKEN to get a channel per pursuit)")
        else:
            st.write("⚠️ Slack not configured — no channel or alert sent")

        status.update(label="Pursuing ✓", state="complete")
    _flash(f"Pursuing — {title[:60]}" + (" · Notion page and Slack channel created" if notion_url and result.get("slack_channel_name") else ""), icon="🎯")


def _change_status(opp: dict, new_status: str, notes: str, current_status: str) -> None:
    """Apply a status change from the card's status controls.

    Routes through the pursuit lifecycle whenever a claimed/active/submitted
    pursuit exists, so the board, reminders, Slack, and the activity log stay
    consistent with the pipeline status. Falls back to the plain status update
    (plus the legacy abandon alert) for opportunities without a pursuit.
    """
    from oppos.outputs.slack_status import notify_status
    from oppos.pursuits import release_claim, transition_pursuit
    from oppos.storage.db import get_pursuit

    from oppos.storage.db import add_pursuit_event, update_pursuit

    sid = opp.get("source_id", "")
    pursuit = get_pursuit(sid)
    p_status = (pursuit or {}).get("status")
    live = p_status in ("evaluating", "active", "submitted")
    pursued = bool(pursuit) and p_status != "released"

    if pursued and not CURRENT_USER.get("is_admin") and (pursuit.get("owner_email") or "").lower() != CURRENT_USER["email"]:
        st.error(f"Owned by {pursuit.get('owner_name') or pursuit.get('owner_email')} ({p_status}) — "
                 "only the owner or an admin can change its status.")
        return

    if pursued and not live:
        # Closed pursuit (won/lost/abandoned): keep the pursuit record consistent with the new status.
        mapping = {"won": "won", "lost": "lost", "skipped": "abandoned", "submitted": "submitted", "in_progress": "active"}
        new_p = mapping.get(new_status, "released")
        set_pipeline_status(sid, new_status, notes=notes or None)
        update_pursuit(sid, status=new_p, closed_at=None if new_p in ("submitted", "active") else datetime.utcnow().isoformat())
        add_pursuit_event(sid, CURRENT_USER.get("email", ""), "status_sync", f"{p_status} → {new_p} via status control: {notes or ''}".strip())
        return

    if new_status == "in_progress" and current_status != "in_progress":
        _pursue_opportunity(opp, reason=notes or "")
        return

    if live and new_status in ("submitted", "won", "lost"):
        if new_status == "submitted" and p_status == "submitted":
            set_pipeline_status(sid, new_status, notes=notes or None)   # already submitted — notes only
        else:
            transition_pursuit(opp, new_status, CURRENT_USER, notes or "")
        return

    if live and new_status == "skipped":
        if p_status == "evaluating":
            release_claim(opp, CURRENT_USER, notes or "Skipped")
        else:
            transition_pursuit(opp, "abandoned", CURRENT_USER, notes or "Skipped")
        set_pipeline_status(sid, "skipped", notes=notes or None)
        return

    set_pipeline_status(sid, new_status, notes=notes or None)
    if not live and new_status in ("skipped", "lost") and current_status in ("qualified", "expiring_soon", "in_progress"):
        notify_status("skipped" if new_status == "skipped" else "lost", opp, CURRENT_USER, notes or "")


def _push_to_notion(opp: dict) -> None:
    """Push an opportunity to the Notion RFP Pipeline database."""
    from oppos.outputs.notion_sync import push_opportunity
    from oppos.storage.db import set_notion_page_id

    sid = opp.get("source_id", "")
    title = opp.get("title", "Untitled")

    with st.status(f"Pushing to Notion: {title[:50]}…", expanded=True) as status:
        st.write("📤 Sending RFP data, scanned documents, and capability profile…")

        # Collect attachment files if they exist on disk
        att_dir = _att_dir(sid)
        attachment_paths = sorted(att_dir.glob("*")) if att_dir.exists() else []
        if attachment_paths:
            st.write(f"📎 {len(attachment_paths)} attachment(s) will be uploaded")

        try:
            page_id = push_opportunity(opp, attachment_paths=attachment_paths or None)
            if page_id:
                set_notion_page_id(sid, page_id)
                clean_id = page_id.replace("-", "")
                status.update(label="Pushed to Notion ✓", state="complete")
                st.success(f"Pushed — [open in Notion](https://notion.so/{clean_id})")
            else:
                from oppos.outputs import notion_sync as _ns
                status.update(label="Notion push failed", state="error")
                st.error(f"Notion did not accept the page: {_ns.LAST_ERROR or 'no reason returned'}")
        except Exception as e:
            status.update(label="Notion push failed", state="error")
            st.error(f"Error: {e}")





def _evidence_html(point) -> str:
    ev = point_evidence(point)
    return f'<div class="evidence-quote">“{_esc(ev)}”</div>' if ev else ""


def _app_link(page: str, sid: str) -> str:
    """Address of one listing (page "") or pursuit (page "desk") in this app; relative when OPPOS_APP_URL is unset."""
    base = (os.environ.get("OPPOS_APP_URL") or "").rstrip("/")
    return f"{base}/{page}?open={sid}" if page else f"{base}/?open={sid}"


def _due_phrase(deadline: str | None) -> str:
    """'Due Nov 2 (in 18 days)', 'Due today', 'Overdue since Oct 10', or 'No deadline'."""
    if not deadline:
        return "No deadline"
    from oppos.storage.db import _parse_deadline
    dl = _parse_deadline(deadline)
    if not dl:
        return f"Due {deadline[:10]}"
    if dl.tzinfo is not None:
        dl = dl.replace(tzinfo=None)
    days = int((dl.date() - datetime.utcnow().date()).days)
    when = dl.strftime("%b %-d")
    if days < 0:
        return f"Overdue since {when}"
    if days == 0:
        return "Due today"
    if days == 1:
        return f"Due tomorrow ({when})"
    return f"Due {when} (in {days} days)"



def _parse_json(raw) -> dict:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw) or {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _score_one(opp: dict, slot) -> None:
    """AI-score one listing from its description (no documents) and keep its status."""
    from oppos.scoring.qualifier import force_score
    from oppos.storage.db import upsert_opportunity
    with slot, st.spinner(f"Scoring {opp.get('title', '')[:50]}…"):
        att_text = opp.get("attachment_text") or ""
        scored = force_score(opp, attachment_text=att_text)
        scored["attachment_text"] = att_text or None
        upsert_opportunity(scored)
        set_pipeline_status(opp["source_id"], opp.get("pipeline_status") or "new",
                            notes=f"Scored from description — {scored.get('fit_score', 0)}/100")
    _flash(f"Scored {scored.get('fit_score', 0)}/100 — {opp.get('title', '')[:60]}")


def _score_batch(batch: list[dict]) -> None:
    """Score several unscored listings from their descriptions, with a progress bar."""
    from oppos.scoring.qualifier import force_score
    from oppos.storage.db import upsert_opportunity
    progress = st.progress(0, text=f"Scoring {len(batch)} listings…")
    ok, errs = 0, []
    for i, opp in enumerate(batch):
        progress.progress(i / len(batch), text=f"Scoring {i + 1}/{len(batch)}: {opp.get('title', '')[:50]}…")
        try:
            att_text = opp.get("attachment_text") or ""
            scored = force_score(opp, attachment_text=att_text)
            scored["attachment_text"] = att_text or None
            upsert_opportunity(scored)
            set_pipeline_status(opp["source_id"], opp.get("pipeline_status") or "new",
                                notes=f"Scored from description — {scored.get('fit_score', 0)}/100")
            ok += 1
        except Exception as e:
            errs.append(f"{opp.get('title', '')[:40]}: {e}")
    progress.progress(1.0, text="Done")
    _flash(f"Scored {ok} listing{'s' if ok != 1 else ''}" + (f" · {len(errs)} failed" if errs else ""), icon="📊" if not errs else "⚠️")



# ── Listing analysis, in plain words ──────────────────────────────────────────

def _fit_reasons_html(s2: dict) -> str:
    """'Why it fits' and 'What to check', three each at most — the part of the analysis a person acts on."""
    fits = [point_claim(s) for s in (s2.get("strengths") or [])][:3]
    checks = [point_claim(r) for r in (s2.get("risks") or [])][:2] + [str(g) for g in (s2.get("knowledge_gaps") or [])]
    checks = checks[:3]
    if not fits and not checks:
        return ""
    col = lambda head, items: (f'<div><div class="rs-head">{head}</div><ul>' + "".join(f"<li>{_esc(i)}</li>" for i in items) + "</ul></div>") if items else ""
    return f'<div class="reasons">{col("Why it fits", fits)}{col("What to check", checks)}</div>'


def _local_time(iso, fmt: str = "%b %-d, %-I:%M %p") -> str:
    """A stored UTC timestamp in the viewer's own time zone (from their browser), e.g. 'Nov 8, 2:05 PM'."""
    try:
        dt = datetime.fromisoformat(str(iso)).replace(tzinfo=timezone.utc)
        tz = getattr(st.context, "timezone", None)
        if tz:
            from zoneinfo import ZoneInfo
            dt = dt.astimezone(ZoneInfo(tz))
        return dt.strftime(fmt)
    except Exception:
        return str(iso or "")[:16]


def _score_is_stale(s2: dict, docs: list[dict]) -> bool:
    """True when documents were read after the score was made (or the score doesn't say what it saw)."""
    b = s2.get("basis") or {}
    reads = [str(d.get("read_at") or "") for d in docs if d["status"] == "read"]
    if not b or not reads:
        return bool(reads)
    return max(reads)[:19] > str(b.get("scored_at") or "")[:19] or not b.get("documents")


def _score_basis(opp: dict, s2: dict) -> str:
    """What the fit score and its analysis were based on, in one plain sentence."""
    b = s2.get("basis") or {}
    when = ""
    if b.get("scored_at"):
        when = " · scored " + _local_time(b["scored_at"])
    if b.get("documents"):
        n = b["documents"]
        return (f"Based on the listing and {n} document{'s' if n != 1 else ''} (up to 60,000 characters, solicitation first){when}. "
                "What the RFP asks, below, covers every page.")
    if b:
        return f"Based on the listing only{when} — preliminary until the RFP's documents are read."
    return ("Scored before OppOS recorded what each score was based on — it may not include the documents."
            if opp.get("attachment_text") else "Based on the listing only — preliminary until the RFP's documents are read.")


def _full_analysis(opp: dict, s2: dict) -> None:
    """Everything else the scorer wrote, folded away."""
    s1 = _parse_json(opp.get("stage1_json"))
    if not s2:
        if s1 and not s1.get("relevant"):
            st.caption(f"The first pass set this aside as not relevant: {s1.get('reason', '')}")
        return
    with st.expander("Full analysis"):
        st.markdown(f'<div class="help" style="margin-bottom:8px">{_esc(_score_basis(opp, s2))}</div>', unsafe_allow_html=True)
        facts = [(l, v) for l, v in (("Closest win", s2.get("similar_win")), ("Industry", s2.get("industry")),
                                      ("Matches the pattern", str(s2.get("pattern_match") or "").replace("_", " ")),
                                      ("Suggested deployment", str(s2.get("deployment_recommendation") or "").replace("_", " ")))
                 if v and v != "other"]
        if facts:
            st.markdown("".join(f'<div class="kv"><span>{_esc(l)}</span>{_esc(str(v))}</div>' for l, v in facts), unsafe_allow_html=True)
        for head, items in (("Strengths", s2.get("strengths")), ("Risks", s2.get("risks"))):
            if items:
                st.markdown(f'<div class="rs-head">{head}</div><ul class="plain">'
                            + "".join(f"<li>{_esc(point_claim(p))}{_evidence_html(p)}</li>" for p in items) + "</ul>", unsafe_allow_html=True)
        if s2.get("knowledge_gaps"):
            st.markdown('<div class="rs-head">Not known from the listing</div><ul class="plain">'
                        + "".join(f"<li>{_esc(str(g))}</li>" for g in s2["knowledge_gaps"]) + "</ul>", unsafe_allow_html=True)
        if s2.get("competitive_notes"):
            st.markdown(f'<div class="rs-head">Competition</div><p class="muted">{_esc(s2["competitive_notes"])}</p>', unsafe_allow_html=True)


def _listing_facts_html(opp: dict) -> str:
    """Contact, dates, source and the description when it says more than the title."""
    contact = " · ".join(_esc(str(c)) for c in (opp.get("contact_name"), opp.get("contact_email"), opp.get("contact_phone")) if c)
    rows = [("Contact", contact or '<span class="muted">Not listed</span>'),
            ("Posted", _esc(str(opp.get("posted_date") or "")[:10]) or '<span class="muted">Unknown</span>'),
            ("Source", _esc(SOURCE_LABELS.get(opp.get("source", ""), opp.get("source", ""))))]
    if opp.get("solicitation_number"):
        rows.append(("Number", _esc(opp["solicitation_number"])))
    desc = (opp.get("description") or "").strip()
    title = (opp.get("title") or "").strip().lower()
    if desc and len(desc) > len(title) + 60:
        rows.append(("Description", _esc(desc[:1500])))
    return '<div class="kvs">' + "".join(f'<div class="kv"><span>{l}</span><div>{v}</div></div>' for l, v in rows) + "</div>"


# ── RFP documents ─────────────────────────────────────────────────────────────

_EVENT_LABELS = {
    "claimed": "Grabbed it", "released": "Put it back", "started": "Started pursuing", "reopened": "Reopened it",
    "updated": "Changed the details", "drafted": "Drafted the response", "draft_notion": "Added the draft to Notion",
    "submitted": "Marked it submitted", "won": "Recorded a win", "lost": "Recorded a loss", "abandoned": "Abandoned it",
    "docs_fetched": "Got the RFP's files", "docs_fetch_failed": "Couldn't get the RFP's files", "docs_read": "Read the documents",
    "docs_added": "Added documents", "requirements_extracted": "Pulled out the requirements", "requirements_failed": "Couldn't pull out the requirements",
    "rescored": "Re-scored the fit", "matrix_read": "Read the requirements matrix", "collab_requested": "Asked to collaborate", "collab_approved": "Approved a collaborator",
    "collab_declined": "Declined a collaborator", "reassigned": "Reassigned it", "slack_channel": "Opened a Slack channel",
    "status_sync": "Synced with Notion", "adopted": "Adopted it",
}
_DOC_TYPES = {"solicitation": "The solicitation", "submission_instructions": "How to submit", "terms_and_conditions": "Terms",
              "form": "Form to fill in", "amendment": "Amendment", "other": "Supporting document",
              "requirements_matrix": "Requirements matrix — answer every row"}


def _size_txt(n) -> str:
    n = int(n or 0)
    return f"{n / 1_048_576:.1f} MB" if n >= 1_048_576 else f"{max(1, n // 1024)} KB"


@st.fragment(run_every=4)
def _reading_progress(sid: str) -> None:
    """Shown while documents are read in the background; reruns the page when the read finishes."""
    from oppos.sources.rfp_documents import job_status
    job = job_status(sid) or {}
    if job.get("state") != "reading":
        st.rerun()
    done, total, cur = int(job.get("done") or 0), int(job.get("total") or 0), job.get("current") or ""
    if job.get("phase") == "requirements":
        st.markdown(f'<div class="doc-reading">{_esc(cur[:1].upper() + cur[1:]) if cur else "Pulling out the requirements"}… '
                    'Nutrient Data Extraction takes a few minutes for a large RFP; you can leave this page.</div>', unsafe_allow_html=True)
        return
    st.markdown(f'<div class="doc-reading">Reading the RFP\'s documents{f" ({min(done + 1, total)} of {total})" if total else ""}'
                f'{": " + _esc(cur) if cur else ""}…</div>', unsafe_allow_html=True)


_MONTHS = "jan feb mar apr may jun jul aug sep oct nov dec".split()


def _same_fact(field: str, a: str, b: str) -> bool:
    """Two documents stating one fact in different words: the same date (month, day, year) or the same portal."""
    if field.endswith("deadline"):
        def key(t: str) -> tuple:
            t = t.lower()
            month = next((i for i, m in enumerate(_MONTHS) if re.search(rf"\b{m}", t)), None)
            nums = re.findall(r"\b\d{1,4}\b", t)
            day = next((int(n) for n in nums if 1 <= int(n) <= 31 and len(n) <= 2 and not re.search(rf"\b{n}\s*(:|am|pm|a\.m|p\.m)", t)), None)
            year = next((int(n) for n in nums if len(n) == 4), None)
            return month, day, year
        ka, kb = key(a), key(b)
        return ka[:2] == kb[:2] and None not in ka[:2] and (ka[2] == kb[2] or None in (ka[2], kb[2]))
    words = lambda t: {w for w in re.findall(r"[a-z0-9@.]{4,}", t.lower())} - {"portal", "system", "state", "only", "through", "submit", "electronic"}
    return bool(words(a) & words(b))


def _render_brief(ext: dict, opp: dict | None = None) -> None:
    """What the RFP asks, from Data Extraction over every document: the solicitation's facts, how it is scored,
    the forms, and every requirement with its file and page."""
    sol = ext.get("solicitation") or {}
    reqs = [r for r in (ext.get("requirements") or []) if not r.get("superseded_by")]
    rows = [(l, sol.get(k)) for l, k in (("Type", "rfp_type"), ("Number", "solicitation_number"), ("Due", "submission_deadline"),
                                          ("Questions due", "questions_deadline"), ("How to submit", "submission_method"),
                                          ("Format", "format_requirements"), ("Contact", "contact_name"), ("Contact email", "contact_email"))
            if sol.get(k) and str(sol.get(k)).strip().lower() != "other"]
    st.markdown('<div class="rs-head">What the RFP asks</div>', unsafe_allow_html=True)
    if rows:
        st.markdown('<div class="kvs" style="margin-top:4px">' + "".join(f'<div class="kv"><span>{_esc(l)}</span><div>{_esc(str(v)[:400])}</div></div>'
                                                                         for l, v in rows) + "</div>", unsafe_allow_html=True)
    for c in [c for c in (ext.get("solicitation_conflicts") or [])
              if c.get("field") in ("submission_deadline", "questions_deadline", "submission_method")
              and not _same_fact(c["field"], str(c.get("kept", "")), str(c.get("other", "")))][:3]:
        if "unknown" in str(c.get("reason", "")) or c.get("reason") == "first document kept":
            st.markdown(f'<p class="muted"><span class="alert">Documents disagree on {_esc(str(c.get("field", "")).replace("_", " "))}:</span> '
                        f'{_esc(str(c.get("kept", ""))[:80])} ({_esc(str(c.get("kept_file", "")))}) vs {_esc(str(c.get("other", ""))[:80])} '
                        f'({_esc(str(c.get("other_file", "")))})</p>', unsafe_allow_html=True)
    crit = ext.get("evaluation_criteria") or []
    forms = ext.get("required_forms") or []
    if crit or forms:
        c1, c2 = st.columns(2)
        if crit:
            c1.markdown('<div class="rs-head">How it is scored</div><ul class="plain">' + "".join(
                f'<li>{_esc(c["criterion"])}{" — " + _esc(c["weight"]) if c.get("weight") else ""}</li>' for c in crit[:12]) + "</ul>", unsafe_allow_html=True)
        if forms:
            c2.markdown('<div class="rs-head">Forms to include</div><ul class="plain">' + "".join(f"<li>{_esc(f)}</li>" for f in forms[:15]) + "</ul>",
                        unsafe_allow_html=True)
    from oppos.drafting.extraction import OBLIGATION_TYPES
    obligations = [r for r in reqs if r.get("document_type") in OBLIGATION_TYPES]
    reqs = [r for r in reqs if r.get("document_type") not in OBLIGATION_TYPES]
    if reqs:
        mand = sum(1 for r in reqs if r.get("mandatory"))
        labels = {"functional": "Functional", "technical": "Technical", "security_compliance": "Security and compliance",
                  "commercial": "Commercial", "company": "About the company", "implementation": "Implementation and support", "other": "Other"}
        by: dict[str, list] = {}
        rank = {"solicitation": 0, "amendment": 0, "submission_instructions": 1}
        for r in sorted(reqs, key=lambda r: (rank.get(r.get("document_type"), 2), not r.get("mandatory"), int(str(r.get("id", "E0"))[1:] or 0))):
            by.setdefault(r.get("category") or "other", []).append(r)
        st.markdown(f'<div class="rs-head" style="margin-top:8px">{len(reqs)} requirements to answer, {mand} mandatory</div>', unsafe_allow_html=True)
        for name, cols in (ext.get("answer_columns") or {}).items():
            n = sum(1 for r in reqs if r.get("file") == name)
            st.markdown(f'<div class="help">{_esc(name)} is a requirements matrix: {n} rows, each answered with '
                        f'{_esc(", ".join(cols[:8]))}.</div>', unsafe_allow_html=True)
        for cat in sorted(by, key=lambda c: list(labels).index(c) if c in labels else 99):
            items = by[cat]
            with st.expander(f"{labels.get(cat, cat.title())} · {len(items)}"):
                st.markdown("".join(
                    f'<div class="req"><div>{_esc(r["text"][:600])}</div><span>{"must · " if r.get("mandatory") else ""}'
                    f'{_esc(r.get("file", ""))}{(" p." + str(r["page"])) if r.get("page") else ""}'
                    f'{" §" + _esc(r["section"]) if r.get("section") else ""}</span></div>' for r in items), unsafe_allow_html=True)
    if obligations:
        with st.expander(f"Obligations in the terms and forms · {len(obligations)}"):
            st.markdown("".join(
                f'<div class="req"><div>{_esc(r["text"][:400])}</div><span>{_esc(r.get("file", ""))}{(" p." + str(r["page"])) if r.get("page") else ""}</span></div>'
                for r in obligations[:400]) + (f'<p class="muted">{len(obligations) - 400} more not shown.</p>' if len(obligations) > 400 else ""),
                unsafe_allow_html=True)
    skipped, errors = ext.get("skipped") or [], ext.get("errors") or []
    if skipped or errors:
        failed = sorted({e.split(":")[0] for e in errors})
        st.markdown(f'<div class="help"><span class="alert">Not analysed: {_esc(", ".join(failed + [x.split(" (")[0] for x in skipped])[:300])}.</span> '
                    'Their text still feeds the fit score and the draft, but their requirements aren\'t listed above.</div>', unsafe_allow_html=True)
        if opp and errors and CURRENT_USER.get("can_work") and st.button("Pull out the requirements again", key=f"reextract_{opp.get('source_id')}", type="tertiary"):
            from oppos.sources.rfp_documents import start_reading
            set_meta(f"extraction:{opp.get('source_id')}", "")  # forget the partial result; the job runs Data Extraction again
            start_reading(opp)
            _flash("Running Data Extraction again on every document — a few minutes", icon="🧩")
            st.rerun()


def _docs_status(docs: list[dict], ext: dict | None, job: dict) -> None:
    """One line at the top of the RFP tab: what OppOS has done with the RFP's documents, and what uses it."""
    n_read = sum(1 for d in docs if d["status"] == "read")
    if job.get("state") == "reading":
        msg = "OppOS is reading this RFP's documents and pulling out the requirements. The analysis appears here when it's done; you can leave the page."
    elif not docs:
        msg = ("No documents yet. Add the RFP's files below: OppOS reads them, pulls out what the RFP asks for, and re-scores the fit. "
               "Draft response works from them.")
    elif ext and ext.get("requirements"):
        reqs = [r for r in ext["requirements"] if not r.get("superseded_by")]
        mand = sum(1 for r in reqs if r.get("mandatory"))
        msg = (f"OppOS read {n_read} document{'s' if n_read != 1 else ''} and pulled out {len(reqs)} requirements ({mand} mandatory). "
               "The fit score, the analysis below and Draft response all use them.")
    else:
        msg = (f"OppOS read {n_read} document{'s' if n_read != 1 else ''}; the fit score and Draft response use them."
               + (" Pulling out the requirements didn't finish — they'll be extracted when you draft." if job.get("extracted") is False else ""))
    st.markdown(f'<div class="collab">{_esc(msg)}</div>', unsafe_allow_html=True)


def _add_documents(opp: dict, k: str, job: dict) -> None:
    """Upload the RFP's files (when the portal needs a login, or OppOS found none): they are read and analysed like
    fetched ones, and the fit is re-scored."""
    from oppos.sources.attachments import _sanitize_filename
    from oppos.sources.extract_text import READABLE_EXTENSIONS
    from oppos.sources.rfp_documents import folder, start_reading
    with st.expander("Add RFP documents"):
        st.markdown('<div class="help">PDF, Word, Excel or PowerPoint, as many as the RFP has. OppOS reads them, pulls out what the RFP '
                    'asks for and re-scores the fit — a few minutes for a large RFP. Files with the same name replace the old copy.</div>',
                    unsafe_allow_html=True)
        files = st.file_uploader("RFP documents", accept_multiple_files=True, key=f"{k}_upload", label_visibility="collapsed",
                                 type=sorted(e.lstrip(".") for e in READABLE_EXTENSIONS) + ["zip"])
        busy = job.get("state") == "reading"
        if files and st.button(f"Add and analyse {len(files)} file{'s' if len(files) != 1 else ''}", key=f"{k}_upload_go",
                               type="primary", disabled=busy):
            d = folder(opp.get("source_id", ""))
            d.mkdir(parents=True, exist_ok=True)
            for f in files:
                path = d / _sanitize_filename(f.name)
                path.write_bytes(f.getvalue())
                if path.suffix.lower() == ".zip":
                    from oppos.sources.attachments import _unzip
                    _unzip(path)
            from oppos.storage.db import add_pursuit_event
            add_pursuit_event(opp.get("source_id", ""), CURRENT_USER["email"], "docs_added", ", ".join(f.name for f in files)[:500])
            start_reading(opp)
            _flash(f"Added {len(files)} file{'s' if len(files) != 1 else ''} — OppOS is reading them now", icon="📄")
            st.rerun()
        if busy:
            st.caption("Wait for the current read to finish, then add more.")


def _render_documents(opp: dict, k: str, auto: bool, docs: list[dict] | None = None) -> None:
    """One list of the RFP's documents, as OppOS read them. `auto`: start reading without asking (a pursuit)."""
    from oppos.sources.rfp_documents import job_status, local_files, start_reading
    from oppos.storage.db import get_documents
    sid = opp.get("source_id", "")
    docs = get_documents(sid) if docs is None else docs
    job = job_status(sid)
    if auto and CURRENT_USER.get("can_work") and not (job and job.get("state") == "reading"):
        from oppos.drafting.extraction import extraction_available
        from oppos.sources.rfp_documents import stored_extraction
        never_extracted = bool(docs) and (job or {}).get("extracted") is None and extraction_available() and not stored_extraction(sid)
        no_summaries = any(d["status"] == "read" and not d.get("summary") for d in docs) and not (job or {}).get("summarized")
        _stored = stored_extraction(sid) if docs else None
        no_matrices = bool(_stored) and not _stored.get("matrices_checked") and not (job or {}).get("matrices")
        if (not docs and not job) or never_extracted or no_summaries or no_matrices:
            start_reading(opp)
            job = job_status(sid)
    if job and job.get("state") == "reading":
        _reading_progress(sid)
        if not docs:
            return
    if not docs:
        if job and job.get("state") == "failed":
            st.markdown(f'<p class="muted">Couldn\'t read the documents: {_esc(job.get("error") or "unknown error")}.</p>', unsafe_allow_html=True)
        elif job and job.get("state") == "done":
            st.markdown('<p class="muted">No documents came with this listing. Open the listing to check for files posted there.</p>', unsafe_allow_html=True)
        if CURRENT_USER.get("can_work") and st.button("Read the RFP's documents" if not job else "Try again", key=f"{k}_docs_read"):
            start_reading(opp)
            _flash("Reading the RFP's documents — the list fills in as they're read", icon="📄")
            st.rerun()
        return
    n_read = sum(1 for d in docs if d["status"] == "read")
    head = (f"{len(docs)} file{'s' if len(docs) != 1 else ''}" + (", all read by OppOS" if n_read == len(docs) else f", {n_read} read by OppOS")
            + ". Download copies for yourself; OppOS already has them.")
    files = {f.name: f for f in local_files(sid)}
    with st.container(horizontal=True, vertical_alignment="center", key=f"{k}_docs_head"):
        st.markdown(f'<p class="muted" style="margin:0">{head}</p>', unsafe_allow_html=True)
        if len(files) > 1:
            def _zip_all(paths=tuple(files.values())) -> bytes:
                import io
                import zipfile
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                    for p_ in paths:
                        zf.write(p_, arcname=p_.name)
                return buf.getvalue()
            stem = re.sub(r"[^A-Za-z0-9]+", "-", (opp.get("solicitation_number") or opp.get("title") or sid))[:60].strip("-") or "rfp"
            st.download_button(f"Download all {len(files)} (zip)", data=_zip_all, file_name=f"{stem}-documents.zip", mime="application/zip",
                               key=f"{k}_dl_all", on_click="ignore")
    from oppos.sources.rfp_documents import stored_extraction
    extraction = stored_extraction(sid) or {}
    per_file: dict[str, int] = {}
    for r in extraction.get("requirements") or []:
        per_file[r.get("file", "")] = per_file.get(r.get("file", ""), 0) + 1
    for d in docs:
        bits = []
        if d.get("doc_type"):
            bits.append(_DOC_TYPES.get(d["doc_type"], d["doc_type"].replace("_", " ").capitalize()))
        if d["status"] == "read":
            bits.append((f'{d["pages"]} page' + ("s" if d["pages"] != 1 else "")) if d.get("pages") else _size_txt(d.get("size")))
            if d.get("read_at"):
                bits.append("read " + _local_time(d["read_at"]))
            if extraction:
                n = per_file.get(d["name"], 0)
                bits.append(f"{n} requirement{'s' if n != 1 else ''} pulled out" if n else "no requirements in it")
        elif d["status"] == "unreadable":
            bits.append('<span class="faint">not read — this file type can\'t be read</span>')
        else:
            bits.append(f'<span class="alert">couldn\'t read: {_esc((d.get("note") or "")[:120])}</span>')
        ext = (Path(d["name"]).suffix.lstrip(".") or "file").upper()[:4]
        summary = d.get("summary") or ("<span class='faint'>Summary coming…</span>" if d["status"] == "read" else "")
        c1, c2 = st.columns([8, 1.4], vertical_alignment="top")
        c1.markdown(f'<div class="doc2"><span class="ext">{_esc(ext)}</span><div><div class="dname">{_esc(d["name"])}</div>'
                    f'<div class="dmeta">{" · ".join(b if b.startswith("<span") else _esc(b) for b in bits)}</div>'
                    + (f'<div class="dsum">{summary if summary.startswith("<span") else _esc(summary)}</div>' if summary else "")
                    + '</div></div>', unsafe_allow_html=True)
        f = files.get(d["name"])
        if f:
            c2.download_button("Download", data=(lambda p=f: p.read_bytes()), file_name=d["name"], key=f"{k}_dl_{d['name']}",
                               type="tertiary", on_click="ignore")
    if CURRENT_USER.get("can_work"):
        missing = [d for d in docs if d["name"] not in files]
        failed = [d for d in docs if d["status"] == "failed"]
        if failed and st.button("Read the failed ones again", key=f"{k}_docs_retry", type="tertiary"):
            start_reading(opp)
            _flash("Reading them again", icon="📄")
            st.rerun()
        if missing and st.button("Get the files again to download them", key=f"{k}_docs_fetch", type="tertiary"):
            from oppos.sources.attachments import download_attachments
            with st.spinner("Getting the files…"):
                got = download_attachments(opp)
            _flash(f"Got {len(got)} file{'s' if len(got) != 1 else ''}", icon="📎")
            st.rerun()


# ── Find RFPs: one row per listing ────────────────────────────────────────────

def _row_meta(opp: dict) -> str:
    state = SOURCE_STATE_MAP.get(opp.get("source", ""), "") or SOURCE_LABELS.get(opp.get("source", ""), "")
    due = opp.get("response_deadline")
    phrase = _due_phrase(due)
    days = None
    try:
        from oppos.pursuits import days_until
        days = days_until(due)
    except Exception:
        pass
    due_html = f'<span class="alert">{_esc(phrase)}</span>' if days is not None and days <= 7 else _esc(phrase)
    bits = [_esc(b) for b in (state, (opp.get("agency") or "")[:70]) if b] + [due_html]
    badge = _reg_badge(PORTAL_REGS.get(opp.get("source") or ""))
    if badge and badge[1] == "reg-bad":
        bits.append('<span class="faint">no account on this portal</span>')
    return " · ".join(bits)


@st.dialog("Listing", width="large")
def _listing_dialog(opp: dict) -> None:
    sid = opp.get("source_id", "")
    s2 = _parse_json(opp.get("stage2_json"))
    score = int(_score_of(opp))
    url = opp.get("url") or ""
    st.markdown(f'<div class="ws-head"><div><div class="ws-title">{_esc(opp.get("title") or "Untitled")}</div>'
                f'<div class="ws-sub">{_row_meta(opp)}</div></div>'
                f'<div class="ws-fit"><b>{score or "–"}</b><span>fit</span></div></div>', unsafe_allow_html=True)
    if s2.get("summary"):
        st.markdown(f'<div class="help">{_esc(_score_basis(opp, s2))}</div><p class="summary">{_esc(s2["summary"])}</p>', unsafe_allow_html=True)
    with st.container(horizontal=True):
        if url:
            st.link_button("Open the listing", url)
        _pool_actions(opp, f"dlg_{sid}", primary=True, in_dialog=True)
    reasons = _fit_reasons_html(s2)
    if reasons:
        st.markdown(reasons, unsafe_allow_html=True)
    st.markdown('<div class="rs-head" style="margin-top:14px">Documents</div>', unsafe_allow_html=True)
    _render_documents(opp, f"dlg_{sid}", auto=False)
    st.markdown(_listing_facts_html(opp), unsafe_allow_html=True)
    _full_analysis(opp, s2)


def _pool_actions(opp: dict, k: str, primary: bool, in_dialog: bool = False) -> None:
    """Grab and Skip (or Reopen in the archive). Grabbing starts reading the documents in the background."""
    from oppos.pursuits import claim_opportunity as _claim
    sid = opp.get("source_id", "")
    status = opp.get("pipeline_status") or "new"
    if not CURRENT_USER.get("can_work"):
        return
    if status in ("won", "lost", "skipped", "expired"):
        if status != "won" and sid not in OPEN_PURSUITS and st.button("Reopen", key=f"{k}_reopen"):
            set_pipeline_status(sid, "new", notes="Reopened from Archive")
            _flash(f"Reopened — {opp.get('title', '')[:60]} is open again", icon="↩️")
            st.rerun()
        return
    if st.button("Grab", key=f"{k}_grab", type="primary" if primary else "secondary"):
        _claim(opp, CURRENT_USER)
        from oppos.sources.rfp_documents import start_reading
        start_reading(opp)
        _flash(f"Grabbed — {opp.get('title', '')[:60]} is on My desk. Its documents are being read.", icon="✋")
        st.rerun()
    with st.popover("Skip", type="tertiary"):
        reason = st.text_input("Why skip it?", key=f"{k}_skip_reason", placeholder="Not a fit — staffing RFP")
        if st.button("Skip it", key=f"{k}_skip_go"):
            _change_status(opp, "skipped", reason or "Skipped", status)
            _flash(f"Skipped — {opp.get('title', '')[:60]}", icon="⏭️")
            st.rerun()
    if in_dialog and not _score_of(opp) and st.button("Get a fit score", key=f"{k}_score", type="tertiary"):
        _score_one(opp, st.container())
        st.rerun()


def _pool_row(opp: dict, k: str, primary: bool) -> None:
    sid = opp.get("source_id", "")
    s2 = _parse_json(opp.get("stage2_json"))
    score = int(_score_of(opp))
    status = opp.get("pipeline_status") or "new"
    with st.container(key=f"row_{k}_{sid}"):
        c0, c1, c2 = st.columns([0.55, 7, 2.1], vertical_alignment="center")
        c0.markdown(f'<div class="score{"" if score >= 50 else " low"}">{score or "–"}</div>', unsafe_allow_html=True)
        with c1:
            if st.button(opp.get("title") or "Untitled", key=f"{k}_open_{sid}", type="tertiary"):
                _listing_dialog(opp)
            meta = _row_meta(opp)
            if status in ("won", "lost", "skipped", "expired"):
                when = str(opp.get("pipeline_updated_at") or opp.get("updated_at") or "")[:10]
                meta = f'{_esc(PIPELINE_LABELS.get(status, status))} {when} · ' + meta
            why = s2.get("summary") or ""
            st.markdown(f'<div class="rmeta">{meta}</div>' + (f'<div class="rwhy">{_esc(why)}</div>' if why else ""), unsafe_allow_html=True)
        with c2, st.container(horizontal=True, horizontal_alignment="right"):
            _pool_actions(opp, f"{k}_{sid}", primary)


# ── Pursuit workspace ─────────────────────────────────────────────────────────

_MANUAL_CHECKLIST = ("questions", "salesforce", "security", "pricing", "legal", "final")  # the rest the app knows itself


def _render_facts(opp: dict, pursuit: dict, draft: dict | None, can_edit: bool, k: str, ext: dict | None = None) -> None:
    """How to submit — each fact once: due, where, our account on the portal, format, contact, next step. What a
    person saved wins; then the draft's reading of the RFP; then the requirements extraction; then the listing."""
    from oppos.pursuits import days_until, save_pursuit_fields
    from oppos.storage.db import upsert_portal_registration
    sid = opp.get("source_id", "")
    sub = dict((draft or {}).get("submission") or {})
    esol = (ext or {}).get("solicitation") or {}
    how = str(esol.get("submission_method") or "")
    if how and not sub.get("method"):
        mail_to = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", how)
        sub["method"] = "email" if mail_to else "mail" if re.search(r"\bmail|hand[- ]deliver|courier", how, re.I) else "portal"
        if mail_to and not sub.get("email_to"):
            sub["email_to"] = mail_to.group(0)
    if not sub.get("questions_deadline") and esol.get("questions_deadline"):
        sub["questions_deadline"] = esol["questions_deadline"]
    if not sub.get("format_requirements") and esol.get("format_requirements"):
        sub["format_requirements"] = [esol["format_requirements"]]
    if draft is None and ext and ext.get("required_forms"):
        draft = {"required_forms": ext["required_forms"]}
    method = (pursuit.get("submission_method") or "unknown").lower()
    if method == "unknown" and str(sub.get("method") or "").lower() in ("portal", "email", "mail", "in_person"):
        method = str(sub["method"]).lower()
    portal_key = str(pursuit.get("portal") or opp.get("source") or "")
    reg = PORTAL_REGS.get(portal_key) or {}
    portal_name = reg.get("display_name") or SOURCE_LABELS.get(opp.get("source", ""), "")
    listing = (f'<div class="help"><a href="{_esc(opp["url"])}" target="_blank">Open the RFP listing</a> — the agency\'s page for this RFP, '
               'where amendments and Q&A answers are posted.</div>') if opp.get("url") else ""

    due_raw = pursuit.get("submission_deadline") or opp.get("response_deadline")
    dleft = days_until(due_raw)
    if due_raw:
        phrase = _due_phrase(due_raw)
        due = _esc(phrase[4:] if phrase.startswith("Due ") else phrase)
    elif esol.get("submission_deadline"):
        due = _esc(str(esol["submission_deadline"])[:80])
    else:
        due = '<span class="unknown">Not known yet</span>'
    if dleft is not None and dleft <= 7:
        due = f'<span class="alert">{due}</span>'
    qa = pursuit.get("qa_deadline") or sub.get("questions_deadline")
    if qa:
        due += f'<div class="help">Questions to the agency are due {_esc(str(qa)[:60])}.</div>'

    if method == "portal":
        where = _esc(portal_name) or "The agency's portal"
        if how and (pursuit.get("submission_method") or "unknown") == "unknown":  # not confirmed by a person yet
            where += f'<div class="help">The RFP says: {_esc(how[:200])}</div>'
        where += listing
    elif method == "email":
        to = str(sub.get("email_to") or opp.get("contact_email") or "")
        where = (f'Email to <a href="mailto:{_esc(to)}">{_esc(to)}</a>' if to else '<span class="unknown">By email; the address isn\'t known yet</span>')
        if sub.get("email_subject"):
            where += f' · subject line <code>{_esc(str(sub["email_subject"]))}</code>'
    elif method == "mail":
        where = "By mail or hand delivery" + (f" · {_esc(opp.get('office') or '')}" if opp.get("office") else "")
    elif method == "in_person":
        where = "In person" + (f" · {_esc(opp.get('office') or '')}" if opp.get("office") else "")
    else:
        where = ('<span class="unknown">Not known yet</span><div class="help">OppOS fills this in from the RFP\'s documents; '
                 'or set it with Edit details.</div>' + listing)

    fmt = [str(x) for x in (sub.get("format_requirements") or []) if not str(x).lower().startswith("required form")][:3]
    forms = [str(x) for x in ((draft or {}).get("required_forms") or [])]
    contact = " · ".join(_esc(str(c)) for c in (opp.get("contact_name"), opp.get("contact_email"), opp.get("contact_phone")) if c) \
        or " · ".join(_esc(str(c)) for c in (esol.get("contact_name"), esol.get("contact_email")) if c)

    def rows_html(rows: list[tuple[str, str]]) -> str:
        return "".join(f'<div class="fact"><span>{l}</span><div>{v}</div></div>' for l, v in rows)

    with st.container(key=f"facts_{k}"):
        st.markdown(rows_html([("Due", due), ("Submit on" if method in ("portal", "unknown") else "Submit", where)]), unsafe_allow_html=True)
        if method in ("portal", "unknown") and portal_key and portal_key != "manual":
            _account_row(portal_key, portal_name or "this portal", reg, pursuit, sid, k)
        more = []
        if fmt or forms:
            more.append(("Format", _esc("; ".join(f[:300] for f in fmt)) + (("<br>" if fmt else "") + f"{len(forms)} required form{'s' if len(forms) != 1 else ''}"
                                                                             " — listed under RFP and documents" if forms else "")))
        more.append(("Contact", contact or ('<span class="unknown">Not in the RFP yet</span>'
                                            + ('<div class="help">Add one with Edit details if you find it.</div>' if can_edit else ""))))
        if pursuit.get("next_action"):
            more.append(("Next step", _esc(pursuit["next_action"][:200])))
        st.markdown(rows_html(more), unsafe_allow_html=True)
        if can_edit:
            _edit_details_popover(opp, pursuit, k)


_REG_HELP = {"unknown": "Nobody has confirmed whether Nutrient can log in here.",
             "not_registered": "We can't submit here until someone requests an account.",
             "in_progress": "An account has been requested; waiting for access.",
             "registered": "We can log in and submit here."}


def _account_row(portal_key: str, portal_name: str, reg: dict, pursuit: dict, sid: str, k: str) -> None:
    """Our account on the portal: one status line and an Update menu that explains each choice."""
    from oppos.pursuits import save_pursuit_fields
    from oppos.storage.db import upsert_portal_registration
    cur = reg.get("status") or pursuit.get("registration_status") or "unknown"
    if cur == "not_required":
        st.markdown('<div class="fact"><span>Our account</span><div>Not needed on this portal</div></div>', unsafe_allow_html=True)
        return
    label = {"unknown": "Not checked yet", "not_registered": "We don't have one", "in_progress": "Requested", "registered": "Registered"}.get(cur, cur)
    with st.container(key=f"acct_{k}"):
        _account_controls(portal_key, portal_name, cur, label, pursuit, sid, k)


def _account_controls(portal_key: str, portal_name: str, cur: str, label: str, pursuit: dict, sid: str, k: str) -> None:
    from oppos.pursuits import save_pursuit_fields
    from oppos.storage.db import upsert_portal_registration
    a, b = st.columns([1, 5.6], vertical_alignment="top")
    a.markdown('<div class="fact-label">Our account</div>', unsafe_allow_html=True)
    with b:
        with st.container(horizontal=True, vertical_alignment="center", gap="small"):
            st.markdown(f'<span class="{"unknown" if cur in ("unknown", "not_registered") else ""}">{_esc(label)}</span>', unsafe_allow_html=True, width="content")
            if CURRENT_USER.get("can_work"):
                with st.popover("Update", type="tertiary"):
                    st.markdown(f"**Does Nutrient have a login on {_esc(portal_name)}?** Your answer applies to every RFP from this portal.")
                    opts = ["unknown", "not_registered", "in_progress", "registered"]
                    names = {"unknown": "Not checked yet", "not_registered": "We don't have an account", "in_progress": "Account requested",
                             "registered": "We're registered"}
                    choice = st.radio("Our account", opts, index=opts.index(cur) if cur in opts else 0, key=f"{k}_reg",
                                      format_func=names.get, captions=[_REG_HELP[o] for o in opts], label_visibility="collapsed")
                    if PORTAL_ACCESS_REQUEST_URL:
                        st.link_button("Request an account from IT", PORTAL_ACCESS_REQUEST_URL)
                        st.caption("Opens the IT service desk form for procurement-portal access. Then choose Account requested above.")
                    if choice != cur:
                        upsert_portal_registration(portal_key, status=choice)
                        save_pursuit_fields(sid, CURRENT_USER, registration_status=choice)
                        _flash(f"{portal_name}: {names[choice].lower()} — saved for every RFP from it", icon="✅")
                        st.rerun()
        st.markdown(f'<div class="help">{_esc(_REG_HELP.get(cur, ""))}</div>', unsafe_allow_html=True)


def _edit_details_popover(opp: dict, pursuit: dict, k: str) -> None:
    from oppos.pursuits import SUBMISSION_METHODS, deadline_date, save_pursuit_fields
    sid = opp.get("source_id", "")
    labels = {"unknown": "Not known yet", "portal": "On a portal", "email": "By email", "mail": "By mail", "in_person": "In person"}
    with st.popover("Edit details", type="tertiary"):
        c1, c2 = st.columns(2)
        sub_dl = c1.date_input("Due", value=deadline_date(pursuit.get("submission_deadline") or opp.get("response_deadline")), key=f"{k}_sub", format="YYYY-MM-DD")
        qa_dl = c2.date_input("Questions due", value=deadline_date(pursuit.get("qa_deadline")), key=f"{k}_qa", format="YYYY-MM-DD")
        _m = pursuit.get("submission_method") or "unknown"
        method = st.selectbox("How it's submitted", SUBMISSION_METHODS, index=SUBMISSION_METHODS.index(_m) if _m in SUBMISSION_METHODS else 0,
                              format_func=lambda v: labels.get(v, v), key=f"{k}_method")
        nxt = st.text_input("Next step", value=pursuit.get("next_action") or "", key=f"{k}_next", placeholder="Send questions by Friday")
        owner_email = owner_name = None
        if CURRENT_USER.get("is_admin"):
            o1, o2 = st.columns(2)
            owner_email = o1.text_input("Owner email", value=pursuit.get("owner_email") or "", key=f"{k}_owner")
            owner_name = o2.text_input("Owner name", value=pursuit.get("owner_name") or "", key=f"{k}_owner_name")
        if st.button("Save", key=f"{k}_save", type="primary"):
            fields = dict(submission_deadline=sub_dl.isoformat() if sub_dl else None, qa_deadline=qa_dl.isoformat() if qa_dl else None,
                          submission_method=method, next_action=nxt.strip() or None)
            if owner_email is not None:
                fields.update(owner_email=owner_email.strip().lower() or None, owner_name=(owner_name or "").strip() or None)
            save_pursuit_fields(sid, CURRENT_USER, **fields)
            _flash("Details saved")
            st.rerun()


def _next_step(opp: dict, pursuit: dict, draft: dict | None, k: str, slot, docs_state: str = "read") -> None:
    """The one yellow button for the stage, then More."""
    from oppos.outputs.slack_alerts import build_sdr_message
    from oppos.pursuits import release_claim, transition_pursuit
    title = opp.get("title") or "Untitled"
    stage = pursuit.get("status") or "active"
    npid = pursuit.get("notion_page_id") or opp.get("notion_page_id")

    def submitted_form(key: str) -> None:
        st.caption("Once the response is in. You'll record the outcome when the agency decides.")
        note = st.text_input("Submission note", key=f"{key}_note", placeholder="Submitted on the portal, confirmation #…")
        if st.button("Mark submitted", key=f"{key}_go", type="primary"):
            transition_pursuit(opp, "submitted", CURRENT_USER, note)
            _flash(f"Submitted — {title[:60]}", icon="📨")
            st.rerun()

    if stage == "evaluating":
        if st.button("Start pursuing", key=f"{k}_start", type="primary"):
            with slot:
                _pursue_opportunity(opp, reason=pursuit.get("reason") or "")
            st.rerun()
    elif stage == "active" and not draft and docs_state == "reading":
        st.button("Draft response", key=f"{k}_draft_wait", type="primary", disabled=True)
    elif stage == "active" and not draft and docs_state == "none":
        # No documents read: drafting would work from the listing's few lines, so ask first.
        with st.popover("Draft response", type="primary"):
            st.markdown("**OppOS hasn't read any of this RFP's documents.** A draft now would be written from the listing's short "
                        "description only, so most answers would be generic or missing.")
            st.markdown("Add the RFP's files under **RFP and documents** first; OppOS reads them and pulls out every requirement "
                        "for the draft.")
            if st.button("Draft from the listing anyway", key=f"{k}_draft_thin"):
                with slot:
                    _run_draft(opp, pursuit)
                st.rerun()
    elif stage == "active" and not draft:
        if st.button("Draft response", key=f"{k}_draft", type="primary"):
            with slot:
                _run_draft(opp, pursuit)
            st.rerun()
    elif stage == "active":
        with st.popover("Mark submitted", type="primary"):
            submitted_form(f"{k}_sub1")
    else:
        with st.popover("Record outcome", type="primary"):
            outcome = st.radio("Outcome", ["won", "lost"], horizontal=True, key=f"{k}_outcome", format_func=str.title)
            out_note = st.text_input("Notes", key=f"{k}_out_note", placeholder="Award details, competitor, debrief…")
            if st.button("Save outcome", key=f"{k}_out_go", type="primary"):
                transition_pursuit(opp, outcome, CURRENT_USER, out_note)
                _flash(f"{outcome.title()} — {title[:60]}", icon="🏁")
                st.rerun()

    with st.popover("More"):
        if stage == "evaluating":
            st.caption("Not worth pursuing? Puts it back in Find RFPs for someone else.")
            if st.button("Put it back in Find RFPs", key=f"{k}_release"):
                release_claim(opp, CURRENT_USER)
                _flash(f"Put back — {title[:60]} is in Find RFPs again", icon="↩️")
                st.rerun()
        if stage == "active" and draft:
            st.caption("Replaces the current draft with a new one (about 15 minutes).")
            if st.button("Write the draft again", key=f"{k}_redraft"):
                with slot:
                    _run_draft(opp, pursuit)
                st.rerun()
            if npid:
                _render_notion_append(opp, pursuit, draft, npid, k, slot)
        if stage == "active" and not draft:
            st.markdown('<div class="rs-head">Already submitted?</div>', unsafe_allow_html=True)
            submitted_form(f"{k}_sub2")
        if stage != "evaluating":
            st.caption("Copies this pursuit's status and details to its page in the team's Notion database.")
            if st.button("Update the Notion page" if npid else "Create the Notion page", key=f"{k}_push"):
                with slot:
                    _push_to_notion(opp)
            st.markdown('<div class="rs-head">Salesforce opportunity request</div>', unsafe_allow_html=True)
            st.caption("Copy this into the SDR Slack channel to get a Salesforce opportunity created.")
            st.code(build_sdr_message(opp), language=None)
        if stage == "active":
            st.markdown('<div class="rs-head">Abandon</div>', unsafe_allow_html=True)
            st.caption("Stops the pursuit and closes it as lost. You can reopen it later from Closed.")
            ab_reason = st.text_input("Why?", key=f"{k}_ab_reason", placeholder="Timeline too tight, requirements changed…")
            if st.button("Abandon this pursuit", key=f"{k}_ab_go"):
                transition_pursuit(opp, "abandoned", CURRENT_USER, ab_reason)
                _flash(f"Abandoned — {title[:60]}", icon="🗑️")
                st.rerun()


def _next_help(stage: str, draft: dict | None, docs_state: str = "read") -> str:
    """One sentence under the yellow button: what it does."""
    if stage == "active" and not draft and docs_state == "reading":
        return "OppOS is still reading the RFP's documents (progress under RFP and documents). Draft response opens when it's done."
    if stage == "active" and not draft and docs_state == "none":
        return "No RFP documents yet. Add them under RFP and documents, then Draft response writes the first draft from them."
    if stage == "evaluating":
        return "Start pursuing creates a Notion page and a Slack channel for this RFP and starts deadline reminders. Not a fit? More → Put it back."
    if stage == "active" and not draft:
        return "Draft response writes a first answer to every requirement, from the RFP and its documents (about 15 minutes)."
    if stage == "active":
        return "Review the answers under Response, send the Word file, then Mark submitted."
    return "Record outcome once the agency announces the award."


def _ask_to_collaborate(opp: dict, pursuit: dict, k: str) -> None:
    """Someone else's pursuit: ask to work on it with them, or see where the request stands."""
    from oppos.pursuits import request_collaboration
    owner = pursuit.get("owner_name") or pursuit.get("owner_email") or "the owner"
    mine = next((c for c in COLLABS.get(opp["source_id"], []) if (c.get("email") or "") == CURRENT_USER["email"]), None)
    if mine and mine.get("status") == "requested":
        st.markdown(f'<span class="help">Request sent — waiting for {_esc(owner)}</span>', unsafe_allow_html=True)
        return
    if not CURRENT_USER.get("can_work"):
        st.markdown(f'<span class="help">{_esc(owner)}\'s pursuit</span>', unsafe_allow_html=True)
        return
    if mine and mine.get("status") == "declined":
        st.markdown(f'<span class="help">{_esc(owner)} declined your last request</span>', unsafe_allow_html=True)
    with st.popover("Ask to collaborate", type="primary"):
        st.markdown(f"**Work on this with {_esc(owner)}.** They get your request on their desk and in Slack; once they approve, "
                    "it shows on your desk and you can edit it too.")
        note = st.text_area("What would you help with?", key=f"{k}_collab_note", placeholder="I know this agency; happy to take the security section.")
        if st.button("Send request", key=f"{k}_collab_go", type="primary"):
            request_collaboration(opp, pursuit, CURRENT_USER, note.strip())
            _flash(f"Request sent to {owner}", icon="🤝")
            st.rerun()


def _collab_requests(opp: dict, pursuit: dict, k: str) -> None:
    """Owner (or an admin): requests to collaborate, each with Approve / Decline."""
    from oppos.pursuits import decide_collaboration
    for c in _collaborators(opp["source_id"], "requested"):
        who = c.get("name") or c["email"]
        with st.container(key=f"{k}_collab_{c['email']}"):
            st.markdown(f'<div class="collab"><b>{_esc(who)}</b> asked to work on this with you.'
                        + (f'<div class="help">“{_esc(c["note"][:300])}”</div>' if c.get("note") else "")
                        + '<div class="help">Approving lets them edit this pursuit and puts it on their desk.</div></div>', unsafe_allow_html=True)
            with st.container(horizontal=True):
                if st.button("Approve", key=f"{k}_collab_yes_{c['email']}", type="primary"):
                    decide_collaboration(opp, pursuit, c["email"], who, True, CURRENT_USER)
                    _flash(f"{who} is now working on this with you", icon="🤝")
                    st.rerun()
                if st.button("Decline", key=f"{k}_collab_no_{c['email']}"):
                    decide_collaboration(opp, pursuit, c["email"], who, False, CURRENT_USER)
                    _flash(f"Declined {who}'s request", icon="✋")
                    st.rerun()


def _render_pursuit_panel(opp: dict, pursuit: dict, events: list[dict]) -> None:
    """One pursuit: header, journey with the next step, how to submit, then Response / RFP and documents / Notes."""
    import json as _json
    from oppos.outputs.slack_pursuits import channel_url
    from oppos.pursuits import CHECKLIST, checklist_state, save_pursuit_fields
    from oppos.storage.db import get_documents

    sid = opp.get("source_id", "")
    k = f"pp_{sid}"
    stage = pursuit.get("status") or "active"
    me = CURRENT_USER["email"]
    is_owner = (pursuit.get("owner_email") or "").lower() == me
    can_edit = bool(CURRENT_USER.get("is_admin")) or _works_on(pursuit, me)
    owner = pursuit.get("owner_name") or pursuit.get("owner_email") or "Unassigned"
    team = [c.get("name") or c["email"] for c in _collaborators(sid)]
    if team:
        owner += " with " + ", ".join(team)
    draft = _parse_json(pursuit.get("draft_json")) or None
    s2 = _parse_json(opp.get("stage2_json"))
    npid = pursuit.get("notion_page_id") or opp.get("notion_page_id")
    state = SOURCE_STATE_MAP.get(opp.get("source", ""), "") or SOURCE_LABELS.get(opp.get("source", ""), "")
    title = _esc(opp.get("title") or "Untitled")
    title_html = f'<a href="{_esc(opp["url"])}" target="_blank">{title}</a>' if opp.get("url") else title
    links = [f'<a href="{_esc(_app_link("desk", sid))}">Link to this pursuit</a>']
    if npid:
        links.append(f'<a href="https://notion.so/{str(npid).replace("-", "")}" target="_blank">Notion</a>')
    if pursuit.get("slack_channel_id"):
        links.append(f'<a href="{channel_url(pursuit["slack_channel_id"])}" target="_blank">#{_esc(pursuit.get("slack_channel_name") or "slack")}</a>')
    st.markdown(
        f'<div class="ws-head"><div><div class="ws-title">{title_html}</div>'
        f'<div class="ws-sub">{_esc(" · ".join(b for b in (state, opp.get("agency") or "", owner) if b))}</div>'
        f'<div class="ws-links">{"".join(links)}</div></div>'
        f'<div class="ws-fit"><b>{int(_score_of(opp)) or "–"}</b><span>fit</span></div></div>', unsafe_allow_html=True)

    steps = [("evaluating", "Grabbed"), ("active", "Pursuing"), ("submitted", "Submitted"), ("decided", "Decided")]
    cur = next((i for i, (s, _) in enumerate(steps) if s == stage), 3)
    journey = '<div class="journey">' + '<i></i>'.join(
        f'<span class="step{" done" if i < cur else " now" if i == cur else ""}">{lbl}</span>' for i, (_, lbl) in enumerate(steps)) + "</div>"
    from oppos.sources.rfp_documents import job_status, stored_extraction
    docs = get_documents(sid)
    ext = stored_extraction(sid) if docs else None
    job = job_status(sid) or {}
    n_read = sum(1 for d in docs if d["status"] == "read")
    docs_state = "reading" if job.get("state") == "reading" else ("read" if n_read else "none")
    j1, j2 = st.columns([3, 2.2], vertical_alignment="center")
    j1.markdown(journey, unsafe_allow_html=True)
    slot = st.container()  # long operations report here, full width
    with j2, st.container(horizontal=True, horizontal_alignment="right"):
        if can_edit:
            _next_step(opp, pursuit, draft, k, slot, docs_state)
        else:
            _ask_to_collaborate(opp, pursuit, k)
    if can_edit:
        st.markdown(f'<div class="next-help">{_esc(_next_help(stage, draft, docs_state))}</div>', unsafe_allow_html=True)
    if is_owner or CURRENT_USER.get("is_admin"):
        _collab_requests(opp, pursuit, k)

    _render_facts(opp, pursuit, draft, can_edit, k, ext)

    # Fixed labels: a label that changes (a count) makes Streamlit treat it as a new tab and jump back to the first.
    t_resp, t_rfp, t_notes = st.tabs(["Response", "RFP and documents", "Notes and activity"])
    with t_resp:
        _render_response(opp, pursuit, draft, k)
    with t_rfp:
        _docs_status(docs, ext, job)
        if s2.get("summary"):
            st.markdown(f'<div class="rs-head">Is it worth pursuing? Fit {int(_score_of(opp)) or "–"}</div>'
                        f'<div class="help">{_esc(_score_basis(opp, s2))}</div>', unsafe_allow_html=True)
            if can_edit and n_read and _score_is_stale(s2, docs) and job.get("state") != "reading":
                st.markdown('<div class="help"><span class="alert">This score was made before OppOS read all of the documents.</span></div>',
                            unsafe_allow_html=True)
                if st.button("Score it again on the documents", key=f"{k}_rescore", type="tertiary"):
                    from oppos.sources.rfp_documents import rescore
                    with st.spinner("Scoring the fit on the listing and the documents…"):
                        rescore(opp)
                    _flash("Fit re-scored on the documents", icon="📊")
                    st.rerun()
            st.markdown(f'<p class="summary">{_esc(s2["summary"])}</p>', unsafe_allow_html=True)
        reasons = _fit_reasons_html(s2)
        if reasons:
            st.markdown(reasons, unsafe_allow_html=True)
        if ext:
            st.markdown('<div style="height:10px"></div>', unsafe_allow_html=True)
            _render_brief(ext, opp)
        st.markdown('<div class="rs-head" style="margin-top:16px">The files</div>', unsafe_allow_html=True)
        _render_documents(opp, k, auto=True, docs=docs)
        if can_edit:
            _add_documents(opp, k, job)
        st.markdown(_listing_facts_html(opp), unsafe_allow_html=True)
        _full_analysis(opp, s2)
    with t_notes:
        state_ = checklist_state(pursuit)
        items = [(key, label) for key, label in CHECKLIST if key in _MANUAL_CHECKLIST]
        st.markdown('<div class="rs-head">Checklist</div>', unsafe_allow_html=True)
        cols = st.columns(2)
        new_state = dict(state_)
        for i, (key, label) in enumerate(items):
            with cols[i % 2]:
                new_state[key] = st.checkbox(label, value=state_[key], key=f"{k}_ck_{key}", disabled=not can_edit)
        if can_edit and new_state != state_:
            save_pursuit_fields(sid, CURRENT_USER, checklist_json=_json.dumps(new_state))
            st.rerun()
        st.markdown('<div class="rs-head" style="margin-top:16px">Activity</div>', unsafe_allow_html=True)
        if not events:
            st.markdown('<p class="muted">Nothing yet.</p>', unsafe_allow_html=True)
        for ev in events:
            ts = _local_time(ev.get("ts"))
            actor = str(ev.get("actor") or "")
            who = "OppOS" if actor in ("OppOS", "system", "") else actor.split("@")[0].replace(".", " ").title()
            what = _EVENT_LABELS.get(str(ev.get("kind") or ""), str(ev.get("kind") or "").replace("_", " ").capitalize())
            detail = str(ev.get("detail") or "")
            st.markdown(f'<div class="event"><span>{_esc(ts)}</span><b>{_esc(who)}</b> · {_esc(what)}'
                        f'{"<div class=help>" + _esc(detail[:400]) + "</div>" if detail else ""}</div>', unsafe_allow_html=True)


def _render_response(opp: dict, pursuit: dict, draft: dict | None, k: str) -> None:
    """The draft: what needs a person first, the Word file and the editor, then every answer folded away."""
    if not draft:
        stage = pursuit.get("status") or "active"
        st.markdown('<p class="muted">' + ("No draft yet. Draft response (above) writes a first answer to every requirement, from the documents under "
                                           "RFP and documents — add them there first if the list is empty."
                                           if stage == "active" else "Start pursuing first; then Draft response writes the first draft.") + "</p>",
                    unsafe_allow_html=True)
        return
    from oppos.dashboard.docauth import response_editor
    from oppos.drafting.document import file_stem, render_markdown
    from oppos.drafting.docx_export import markdown_to_docx
    reqs = draft.get("requirements") or []
    stats = draft.get("stats") or {}
    when = str(draft.get("generated_at", ""))[:10]
    try:
        when = datetime.fromisoformat(when).strftime("%b %-d")
    except ValueError:
        pass
    needs = [r for r in reqs if "needs_human" in (r.get("basis") or [])]  # the drafter's own count (stats.needs_human)
    reg = PORTAL_REGS.get(str(pursuit.get("portal") or "")) or {}
    stem = file_stem(opp)
    open_key = f"{k}_doc_open"
    md = render_markdown(draft, opp, author=CURRENT_USER.get("name", ""), pursuit=dict(pursuit, portal_name=reg.get("display_name") or ""))
    subject = " — ".join(x for x in ((opp.get("agency") or "").strip(), (opp.get("solicitation_number") or "").strip()) if x) or (opp.get("title") or "")[:60]

    with st.container(horizontal=True, vertical_alignment="center"):
        st.markdown(f'<p class="draftline"><b>Draft from {_esc(when)}.</b> {stats.get("requirements", len(reqs))} answers, '
                    f'{len(needs)} need you.' + (" Appended to Notion." if (draft.get("notion_append") or {}).get("complete") else "") + "</p>",
                    unsafe_allow_html=True)
        st.download_button("Download Word", data=lambda: markdown_to_docx(md, subject=subject, author=CURRENT_USER.get("name", "")),
                           file_name=f"{stem}.docx", key=f"{k}_doc_docx", on_click="ignore",
                           mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        if st.button("Close the editor" if st.session_state.get(open_key) else "Edit or export PDF", key=f"{k}_doc_toggle", type="tertiary"):
            st.session_state[open_key] = not st.session_state.get(open_key)
            st.rerun()
    if st.session_state.get(open_key):
        response_editor(md, stem, DOCAUTH_LICENSE_KEY, viewer_license_key=VIEWER_LICENSE_KEY,
                        docx=markdown_to_docx(md, subject=subject, author=CURRENT_USER.get("name", "")))
    if needs:
        st.markdown('<div class="todo">' + "".join(
            f'<div class="todo-row"><span class="tid">{_esc(r.get("id", ""))}</span><div>{_esc(str(r.get("text", ""))[:160])}'
            f'<div class="twhy">{_esc(str(r.get("human_todo") or "Low confidence — check this answer")[:220])}</div></div></div>'
            for r in needs) + "</div>", unsafe_allow_html=True)
    with st.expander(f"Every answer ({len(reqs)})"):
        if draft.get("executive_summary"):
            st.markdown('<div class="rs-head">Executive summary</div>', unsafe_allow_html=True)
            st.write(draft["executive_summary"])
        for r in reqs:
            st.markdown(f'<div class="ans-head">{_esc(r.get("id", ""))}{" · " + _esc(r["section"]) if r.get("section") else ""}'
                        f'<span>{_esc(str(r.get("confidence", "")))} confidence</span></div>'
                        f'<div class="ans-req">{_esc(r.get("text", ""))}</div>', unsafe_allow_html=True)
            st.write(r.get("response", ""))
        for head, key in (("Questions to ask the agency", "open_questions"), ("Assumptions", "assumptions"), ("Do not claim", "do_not_claim")):
            if draft.get(key):
                st.markdown(f'<div class="rs-head">{head}</div><ul class="plain">' + "".join(f"<li>{_esc(x)}</li>" for x in draft[key]) + "</ul>",
                            unsafe_allow_html=True)



def render_empty(message: str) -> None:
    st.markdown(f'<div class="empty-state"><h3>{message}</h3></div>', unsafe_allow_html=True)


def _run_draft(opp: dict, pursuit: dict) -> None:
    """Stage 3: draft the response for a pursued RFP, store it, note it in Slack."""
    from oppos.drafting import compliance_status, draft_response
    from oppos.outputs import slack_pursuits as sp
    from oppos.storage.db import add_pursuit_event, save_draft

    sid = opp.get("source_id", "")
    title = opp.get("title", "Untitled")
    comp = compliance_status()
    with st.status(f"Drafting response: {title[:50]}…", expanded=True) as status:
        from oppos.sources.rfp_documents import local_files, read_rfp_documents
        st.write("📄 Reading the RFP's documents…")
        res = read_rfp_documents(opp, on_progress=lambda name, i, n: st.write(f"   {i + 1}/{n} {name}"))
        att = opp.get("attachment_text") or ""
        st.write(f"📄 Using the RFP description" + (f" and {res['read']} document{'s' if res['read'] != 1 else ''}" if res["read"]
                                                     else " only — no documents came with this listing"))
        st.write("🔒 Security items get the Trust Center standard answer (NDA access on request); explicit asks for a specific statement or artifact are "
                 + ("answered from the approved compliance file" if comp["approved"] else "marked [SECURITY TO CONFIRM]"))

        # Nutrient Data Extraction maps every document (PDF and Office) to a page-cited requirements schema. Grabbing
        # the RFP already ran it in the background; it runs here only when the documents changed since or it never did.
        from oppos.drafting.extraction import extraction_available
        from oppos.sources.rfp_documents import extract_requirements, stored_extraction
        extracted = stored_extraction(sid)
        if extracted:
            st.write(f"🧩 Using the requirements already pulled from the documents ({len(extracted.get('requirements') or [])})")
        elif res["read"] and extraction_available():
            extracted = extract_requirements(opp, on_progress=lambda m: st.write(f"🧩 {m}"))
        if extracted:
            from oppos.drafting.extraction import DRAFT_MAX_REQUIREMENTS, drafting_subset
            st_ = extracted.get("stats") or {}
            if extracted.get("requirements"):
                st.write(f"✓ Nutrient Data Extraction: {st_.get('requirements', 0)} requirements ({st_.get('mandatory', 0)} mandatory) from "
                         f"{extracted.get('pages', 0)} pages")
            extracted, left_out = drafting_subset(extracted)
            if left_out:
                st.write(f"ℹ️ Answering {len(extracted['requirements'])} of them one by one (mandatory first, up to {DRAFT_MAX_REQUIREMENTS}); "
                         f"{left_out} more are listed under RFP and documents. Terms and forms are acknowledged, not answered item by item.")
            for sk in extracted.get("skipped", []):
                st.write(f"⚠️ Skipped {sk}")
            for er in extracted.get("errors", []):
                st.write(f"⚠️ Extraction error — {er}")
            if not extracted.get("requirements"):
                # A forms-only or instructions-only package yields no requirement items but still carries the
                # authoritative deadline / method / forms / criteria — keep them; discard only an empty result.
                if not any(extracted.get(k) for k in ("solicitation", "required_forms", "evaluation_criteria")):
                    extracted = None
        try:
            draft = draft_response(opp, attachment_text=att, extracted=extracted, on_progress=lambda m: st.write(f"✍️ {m}"))
        except Exception as e:
            status.update(label="Draft failed", state="error")
            st.error(f"Drafting failed: {e}")
            return
        save_draft(sid, draft)
        add_pursuit_event(sid, CURRENT_USER.get("email", ""), "drafted",
                          f"{draft['stats']['requirements']} requirements, {draft['stats']['needs_human']} need a human")
        from oppos.outputs.slack_status import notify_status
        notify_status("draft", opp, CURRENT_USER, pursuit=pursuit,
                      extra=f"{draft['stats']['requirements']} requirements drafted · {draft['stats']['high_confidence']} high confidence · "
                            f"{draft['stats']['needs_human']} need a human · review on My desk, then append to Notion")
        status.update(label="Draft ready ✓", state="complete")
    _flash(f"Draft ready — {draft['stats']['requirements']} requirements, {draft['stats']['needs_human']} need a human"
           + (" · output was truncated (raise DRAFT_MAX_TOKENS)" if draft.get("truncated") else ""), icon="✍️")




def _render_notion_append(opp: dict, pursuit: dict, _draft: dict, npid: str, k: str, slot) -> None:
    """'Append draft to Notion' with resumable batches (lives in the More menu)."""
    from oppos.storage.db import add_pursuit_event as _add_event, save_draft as _save_draft
    sid = opp.get("source_id", "")
    _prog = _draft.get("notion_append") or {}
    _same = _prog.get("page_id") == str(npid) and _prog.get("generated_at") == _draft.get("generated_at")
    _complete = bool(_prog.get("complete") and _same)
    _resume = _same and not _prog.get("complete")
    _btn = f"Resume Notion append ({_prog.get('done', 0)}/{_prog.get('total', '?')})" if _resume else ("Draft appended to Notion ✓" if _complete else "Append draft to Notion")
    if st.button(_btn, key=f"{k}_draft_notion", use_container_width=True, disabled=_complete):
        from oppos.outputs.notion_sync import append_response_draft

        def _on_batch(done: int, total: int, base: int | None = None) -> None:
            _draft["notion_append"] = {"page_id": str(npid), "generated_at": _draft.get("generated_at"),
                                       "done": done, "total": total, "complete": done >= total, "base": base}
            _save_draft(sid, _draft)
        # If a batch landed on the page but its checkpoint could not be saved, the true position is kept for this
        # session so the next click resumes from there instead of the stale persisted one.
        _sess_key = f"{k}_notion_true_done"
        _sess = st.session_state.get(_sess_key) or {}
        _start = _prog.get("done", 0) if _resume else 0
        if _sess.get("page_id") == str(npid) and _sess.get("generated_at") == _draft.get("generated_at"):
            _start = max(_start, int(_sess.get("done", 0)))
        with slot, st.spinner("Appending the draft to the Notion page…"):
            res = append_response_draft(str(npid), _draft, start_batch=_start, on_batch=_on_batch,
                                        base_children=(_prog.get("base") if _resume else None))
        if res["ok"]:
            st.session_state.pop(_sess_key, None)
            _add_event(sid, CURRENT_USER.get("email", ""), "draft_notion", f"Draft appended to Notion page ({res['total']} batches)")
            _flash("Draft appended to the Notion page", icon="📝")
            st.rerun()
        with slot:
            if res.get("ambiguous"):
                if res.get("base") is not None:
                    _on_batch(res["done"], res["total"], res["base"])  # keep the page baseline so the retry can reconcile
                st.error(f"Notion append stopped at batch {res['done'] + 1}/{res['total']}: {res['error']}. Nothing further is written "
                         "until the page can be read; the next attempt reads it first and skips any batch that is already there.")
            elif res.get("checkpoint_failed"):
                st.session_state[_sess_key] = {"page_id": str(npid), "generated_at": _draft.get("generated_at"), "done": res["done"]}
                st.error(f"Notion append paused after batch {res['done']}/{res['total']}: {res['error']}. Click again in this session to "
                         f"resume from batch {res['done'] + 1}; the saved checkpoint is behind, so do not resume from another browser "
                         "until this one finishes.")
            else:
                st.error(f"Notion append stopped at batch {res['done']}/{res['total']} — {res['error']}. Click again to resume; "
                         "earlier batches will not be duplicated.")



def _unclaimed(rows: list[dict]) -> tuple[list[dict], int]:
    """Split Find-RFPs rows into (shown, number hidden because they belong to a desk).

    Anything with a pursuit record — claimed, pursuing, submitted or closed — is managed from
    its owner's desk and never rendered (or counted) in the shared pool. The pool is also
    strict about exclusions, so an excluded-source row can't be re-claimed from here.
    """
    pool = [r for r in rows if r.get("source") not in EXCLUDED_SOURCES]
    kept = [r for r in pool if r.get("source_id") not in PURSUED_IDS]
    return kept, len(pool) - len(kept)



def _ago(iso: str | None) -> str:
    if not iso:
        return "never"
    try:
        secs = (datetime.now(timezone.utc) - datetime.fromisoformat(iso).replace(tzinfo=timezone.utc)).total_seconds()
    except (ValueError, TypeError):
        return str(iso)
    if secs < 60:
        return "just now"
    if secs < 3600:
        return f"{int(secs // 60)}m ago"
    if secs < 86400:
        return f"{int(secs // 3600)}h ago"
    return f"{int(secs // 86400)}d ago"


def _show_more(rows: list[dict], key: str, render, page: int = 25) -> None:
    shown = st.session_state.get(key, page)
    for opp in rows[:shown]:
        render(opp)
    if shown < len(rows):
        if st.button(f"Show more ({len(rows) - shown} remaining)", key=f"{key}_more", use_container_width=True):
            st.session_state[key] = shown + page
            st.rerun()





def page_pool() -> None:
    """Find RFPs — one row per open listing; Good fit / All open / Archive."""
    _welcome()

    def _set_aside(r: dict) -> bool:
        """Rejected by the first pass and never looked at by a person: stored (so it is not re-scanned) but not a
        listing to show. Notes written by the app itself (the deadline sweep, auto-expiry) do not count as a person."""
        notes = str(r.get("pipeline_notes") or "")
        if _score_of(r) or (notes and not notes.startswith(("Deadline within", "Auto-"))):
            return False
        s1 = _parse_json(r.get("stage1_json"))
        return bool(s1) and not s1.get("relevant")
    all_rows = get_all_scored(0)
    open_rows, claimed_n = _unclaimed([r for r in all_rows if (r.get("pipeline_status") or "new") in ("new", "qualified", "expiring_soon") and not _set_aside(r)])
    good = [r for r in open_rows if _score_of(r) >= GOOD_FIT]

    _open_q = st.query_params.get("open")
    v1, v2 = st.columns([4, 1.2], vertical_alignment="center")
    with v1:
        view = st.segmented_control("Show", ["Good fit", "All open", "Archive"], default="Good fit", key="pool_view",
                                    label_visibility="collapsed", required=True)
    with v2, st.container(horizontal=True, horizontal_alignment="right"):
        if st.button("Add an RFP", disabled=not CURRENT_USER.get("can_work")):
            _manual_rfp_dialog()

    if view == "Archive":
        rows, _ = _unclaimed([r for r in all_rows if (r.get("pipeline_status") or "new") in ("won", "lost", "skipped", "expired")])
        rows.sort(key=lambda r: r.get("pipeline_updated_at") or r.get("updated_at") or "", reverse=True)
        st.markdown(f'<p class="muted">{len(rows):,} archived: skipped, expired, won or lost.</p>', unsafe_allow_html=True)
    else:
        rows = good if view == "Good fit" else open_rows
        rows = sorted(rows, key=lambda r: (-_score_of(r), r.get("response_deadline") or "9999"))
        line = (f"{len(good)} of {len(open_rows)} open listings fit well (fit {GOOD_FIT}+)" if view == "Good fit"
                else f"{len(open_rows)} open listings, best fit first")
        if claimed_n:
            line += f" · {claimed_n} on desks"
        line += f" · checked daily, last scan {_ago(_cached_meta('last_scan'))}"
        st.markdown(f'<p class="muted">{line}</p>', unsafe_allow_html=True)
        if not CURRENT_USER.get("can_work"):
            st.caption(NO_ACCESS_NOTE)
    if _open_q:  # shared link to one listing: open it
        hit = next((r for r in all_rows if r.get("source_id") == _open_q), None)
        if hit and st.session_state.get("pool_deeplink") != _open_q:
            st.session_state["pool_deeplink"] = _open_q
            _listing_dialog(hit)
    if not rows:
        render_empty("Nothing here. Try All open." if view == "Good fit" else "Nothing here yet.")
        return
    first = next((r["source_id"] for r in rows if CURRENT_USER.get("can_work")), None)
    _show_more(rows, f"pool_show_{view}", lambda o: _pool_row(o, "pool", primary=o["source_id"] == first and view != "Archive"))


def page_desk() -> None:
    """My desk — the person's pursuits in a rail on the left, the selected one on the right. Team shows everyone's."""
    _welcome(only_if_asked=True)
    from oppos.pursuits import days_until as _du, reopen_pursuit, stage_label
    from oppos.storage.db import get_opps_by_ids, get_pursuit_events_for

    me = CURRENT_USER["email"]
    all_p = _cached_pursuits()
    _open_q = st.query_params.get("open")
    if _open_q and st.session_state.get("desk_deeplink") != _open_q:  # deep link from Slack or a shared address
        st.session_state["desk_deeplink"] = _open_q
        target = next((p for p in all_p if p["source_id"] == _open_q), None)
        if target:
            mine = _works_on(target, me)
            st.session_state["pursuit_view"] = "Mine" if mine else "Team"
            st.session_state[f"desk_sel_{'Mine' if mine else 'Team'}"] = _open_q
        else:
            _flash("That RFP is no longer on anyone's desk.", icon="ℹ️")

    rail, work = st.columns([1.15, 3], gap="large")
    with rail:
        view = st.segmented_control("View", ["Mine", "Team"], default="Mine", key="pursuit_view", label_visibility="collapsed", required=True)
        # Mine: what I own or was approved to work on. Team: everyone else's — ask to collaborate from there.
        rows_p = [p for p in all_p if _works_on(p, me) != (view == "Team")]
        order = {"evaluating": 1, "active": 0, "submitted": 2}
        live = sorted([p for p in rows_p if p.get("status") in order],
                      key=lambda p: (order[p["status"]], p.get("submission_deadline") or "9999"))
        closed = sorted([p for p in rows_p if p.get("status") in ("won", "lost", "abandoned")],
                        key=lambda x: x.get("closed_at") or x.get("updated_at") or "", reverse=True)
        opps = get_opps_by_ids([p["source_id"] for p in live] + [p["source_id"] for p in closed[:50]])
        if not live:
            st.markdown('<p class="muted">' + ("Nobody else has an RFP on their desk." if view == "Team" else "Nothing on your desk yet. Grab an RFP in Find RFPs and it lands here.") + "</p>",
                        unsafe_allow_html=True)
        else:
            ids = [p["source_id"] for p in live]
            key = f"desk_sel_{view}"
            if st.session_state.get(key) not in ids:
                st.session_state[key] = ids[0]

            def caption(p: dict) -> str:
                o = opps.get(p["source_id"]) or {}
                dl = _du(p.get("submission_deadline") or o.get("response_deadline"))
                due = "" if dl is None else ("overdue" if dl < 0 else "due today" if dl == 0 else f"{dl} days left")
                bits = [stage_label(p["status"]), SOURCE_STATE_MAP.get(o.get("source", ""), ""), due]
                if view == "Team" or (p.get("owner_email") or "").lower() != me:
                    bits.append((p.get("owner_name") or p.get("owner_email") or "").split(" ")[0] + "'s")
                n_req = len(_collaborators(p["source_id"], "requested"))
                if n_req and (p.get("owner_email") or "").lower() == me:
                    bits.append(f"{n_req} asking to collaborate")
                return " · ".join(b for b in bits if b)
            with st.container(key="desk_rail"):
                st.radio("Pursuits", ids, key=key, label_visibility="collapsed",
                         format_func=lambda s: ((opps.get(s) or {}).get("title") or s)[:90],
                         captions=[caption(p) for p in live])
        if closed:
            with st.expander(f"Closed ({len(closed)})"):
                for p_ in closed[:50]:
                    o = opps.get(p_["source_id"]) or {}
                    st.markdown(f'<div class="closed-row">{_esc((o.get("title") or p_["source_id"])[:80])}'
                                f'<span>{_esc(stage_label(p_.get("status")))} · {_esc(str(p_.get("closed_at") or p_.get("updated_at") or "")[:10])}</span></div>',
                                unsafe_allow_html=True)
                    if o and CURRENT_USER.get("can_work") and st.button("Reopen", key=f"reopen_closed_{p_['source_id']}", type="tertiary"):
                        reopen_pursuit(o, CURRENT_USER)
                        st.session_state["desk_sel_Mine"] = p_["source_id"]
                        st.session_state["pursuit_view"] = "Mine"
                        _flash(f"Reopened — {o.get('title', '')[:60]} is back in Pursuing", icon="↩️")
                        st.rerun()

    with work:
        if not live:
            return
        selected = st.session_state.get(f"desk_sel_{view}")
        if st.query_params.get("open") != selected:
            st.query_params["open"] = selected  # the address bar is the share link for this pursuit
            st.session_state["desk_deeplink"] = selected
        p_ = next(p for p in live if p["source_id"] == selected)
        o = opps.get(selected)
        if o:
            _render_pursuit_panel(o, p_, get_pursuit_events_for([selected], limit_per=40).get(selected, []))


def page_admin() -> None:
    """Admin — people, pursuits, sources, listings, portals, system."""
    _welcome(only_if_asked=True)
    from oppos.storage.db import get_source_health as _get_source_health
    health = [r for r in _get_source_health() if r.get("source") not in EXCLUDED_SOURCES]
    if not CURRENT_USER.get("is_admin"):
        st.markdown('<p class="muted">Admin tools are for admins (set in OPPOS_ADMINS). Below: how each source did on its last scan.</p>',
                    unsafe_allow_html=True)
        st.markdown(_render_source_health(health), unsafe_allow_html=True)
        return

    t_people, t_pursuits, t_sources, t_listings, t_portals, t_system = st.tabs(
        ["People", "Pursuits", "Sources", "Listings", "Portals", "System"])

    with t_people:
        _admin_people()
    with t_pursuits:
        _admin_pursuits()
    with t_sources:
        _admin_sources(health)
    with t_listings:
        _admin_listings()
    with t_portals:
        _admin_portals()
    with t_system:
        _admin_system()


def _admin_people() -> None:
    from oppos.pursuits import OPEN_STAGES
    stored = _cached_meta("members")
    env_members = member_emails(None)
    try:
        stored_list = [str(e) for e in json.loads(stored)] if stored else []
    except (TypeError, ValueError):
        stored_list = []
    everyone = sorted(set(member_emails(stored)) | {(p.get("owner_email") or "").lower() for p in _ALL_PURSUITS if p.get("owner_email")})
    rows = []
    for email in everyone:
        mine = [p for p in _ALL_PURSUITS if (p.get("owner_email") or "").lower() == email]
        last = max((str(p.get("updated_at") or "") for p in mine), default="")
        rows.append({"Person": email, "Grabbed": sum(p.get("status") == "evaluating" for p in mine),
                     "Pursuing": sum(p.get("status") == "active" for p in mine), "Submitted": sum(p.get("status") == "submitted" for p in mine),
                     "Won": sum(p.get("status") == "won" for p in mine), "Lost / abandoned": sum(p.get("status") in ("lost", "abandoned") for p in mine),
                     "Last activity": last[:10]})
    st.markdown('<div class="rs-head">Who is working what</div>', unsafe_allow_html=True)
    if rows:
        st.dataframe(rows, hide_index=True, use_container_width=True)
    st.markdown('<div class="rs-head" style="margin-top:16px">Who can grab and work RFPs</div>', unsafe_allow_html=True)
    txt = st.text_area("Member emails, one per line", value="\n".join(stored_list), key="members_txt", height=140,
                       placeholder="name@nutrient.io", label_visibility="collapsed")
    all_members = member_emails(stored)
    st.caption(("Access is open: anyone who signs in can grab and work RFPs. Add emails to restrict it." if not all_members else
                f"{len(all_members)} can grab and work RFPs" + (f" ({len(env_members)} from OPPOS_MEMBERS)" if env_members else "")
                + "; everyone else can browse.") + " Admins (OPPOS_ADMINS) always can.")
    if st.button("Save members", key="members_save", type="primary"):
        new = sorted({e.strip().lower() for e in txt.splitlines() if e.strip()})
        set_meta("members", json.dumps(new))
        _flash(f"Members saved — {len(new)} listed")
        st.rerun()


def _admin_pursuits() -> None:
    from oppos.pursuits import OPEN_STAGES, release_claim, stage_label, transition_pursuit
    from oppos.storage.db import add_pursuit_event, get_opps_by_ids, update_pursuit
    open_p = [p for p in _ALL_PURSUITS if p.get("status") in OPEN_STAGES]
    if not open_p:
        st.markdown('<p class="muted">No open pursuits.</p>', unsafe_allow_html=True)
        return
    opps = get_opps_by_ids([p["source_id"] for p in open_p])
    label = lambda p: f'{(opps.get(p["source_id"]) or {}).get("title", p["source_id"])[:70]} — {p.get("owner_name") or p.get("owner_email") or "unassigned"}'
    st.dataframe([{"RFP": (opps.get(p["source_id"]) or {}).get("title", p["source_id"]), "Owner": p.get("owner_name") or p.get("owner_email"),
                   "Stage": stage_label(p.get("status")), "Due": str(p.get("submission_deadline") or "")[:10],
                   "Updated": str(p.get("updated_at") or "")[:10]} for p in open_p], hide_index=True, use_container_width=True)
    st.markdown('<div class="rs-head" style="margin-top:16px">Change one</div>', unsafe_allow_html=True)
    pick = st.selectbox("Pursuit", open_p, format_func=label, key="adm_pursuit", label_visibility="collapsed")
    opp = opps.get(pick["source_id"]) or {"source_id": pick["source_id"]}
    c1, c2 = st.columns([2, 1], vertical_alignment="bottom")
    people = sorted(set(member_emails(_cached_meta("members"))) | {(p.get("owner_email") or "").lower() for p in _ALL_PURSUITS if p.get("owner_email")})
    new_owner = c1.selectbox("Give it to", people, index=people.index((pick.get("owner_email") or "").lower()) if (pick.get("owner_email") or "").lower() in people else 0,
                             key="adm_owner") if people else c1.text_input("Give it to (email)", key="adm_owner_txt")
    if c2.button("Reassign", key="adm_reassign", use_container_width=True):
        update_pursuit(pick["source_id"], owner_email=new_owner.lower(), owner_name=new_owner.split("@")[0].replace(".", " ").title())
        add_pursuit_event(pick["source_id"], CURRENT_USER["email"], "reassigned", f"to {new_owner} by an admin")
        _flash(f"Reassigned to {new_owner}")
        st.rerun()
    a1, a2 = st.columns(2)
    if a1.button("Put it back in Find RFPs", key="adm_release", use_container_width=True):
        release_claim(opp, CURRENT_USER, reason="Put back by an admin")
        _flash("Put back in Find RFPs", icon="↩️")
        st.rerun()
    if pick.get("status") != "evaluating" and a2.button("Close it as abandoned", key="adm_abandon", use_container_width=True):
        transition_pursuit(opp, "abandoned", CURRENT_USER, "Closed by an admin")
        _flash("Closed as abandoned", icon="🗑️")
        st.rerun()


def _admin_sources(health: list[dict]) -> None:
    from oppos.storage.db import archive_sources, count_active_by_sources, list_sources_in_db, set_excluded_sources
    from oppos.sources.registry import _load_registry
    st.markdown(f'<p class="muted">The scan runs daily on GitHub; last scan {_ago(_cached_meta("last_scan"))}. '
                'Running one here takes 10–20 minutes and alerts Slack like the daily one.</p>', unsafe_allow_html=True)
    registry = _load_registry()
    c1, c2, c3 = st.columns([2.2, 1, 1], vertical_alignment="bottom")
    one = c1.selectbox("Source", [""] + sorted(registry, key=lambda k: registry[k][0]), key="adm_src",
                       format_func=lambda k: "Every source" if not k else registry[k][0])
    if c2.button("Scan now", key="adm_scan", type="primary", use_container_width=True):
        from oppos.pipeline import run_scan
        prog = st.progress(0, text="Starting…")
        stats = run_scan(sources=[(one, registry[one][0], registry[one][1])] if one else None,
                         on_progress=lambda i, n, name: prog.progress(i / max(n, 1), text=f"Scanning {name} ({i + 1}/{n})"))
        set_meta("last_scan", datetime.utcnow().isoformat())
        _flash(f"Scan done — {stats['fetched']} listings checked, {stats['new']} new" + (f", {len(stats['errors'])} source errors" if stats["errors"] else ""), icon="🔎")
        st.rerun()
    c3.link_button("Daily scan runs", "https://github.com/brperdomo/OppOS/actions/workflows/scan.yml", use_container_width=True)
    st.markdown('<div class="rs-head" style="margin-top:16px">How each source did</div>', unsafe_allow_html=True)
    st.markdown(_render_source_health(health), unsafe_allow_html=True)

    st.markdown('<div class="rs-head" style="margin-top:16px">Excluded sources</div>', unsafe_allow_html=True)
    st.caption("Hidden from every list, skipped by scans, never alerted. Pursuits already on a desk stay.")
    db_sources = dict(list_sources_in_db())
    keys = sorted(set(SOURCE_LABELS) | set(db_sources) | EXCLUDED_SOURCES)
    sel = st.multiselect("Excluded sources", keys, default=sorted(EXCLUDED_SOURCES), key="excluded_sources_select", label_visibility="collapsed",
                         format_func=lambda k: SOURCE_LABELS.get(k, k) + ("" if k in SOURCE_LABELS else " (retired)") + (f" · {db_sources[k]} rows" if db_sources.get(k) else ""))
    e1, e2 = st.columns([1, 2])
    if e1.button("Save exclusions", key="excluded_save", use_container_width=True):
        set_excluded_sources(sel)
        _flash("Exclusions saved")
        st.rerun()
    n_active = count_active_by_sources(sorted(EXCLUDED_SOURCES)) if EXCLUDED_SOURCES else 0
    if n_active and e2.button(f"Archive their {n_active} open listings", key="excluded_archive", use_container_width=True):
        _flash(f"Archived {archive_sources(sorted(EXCLUDED_SOURCES))} listings")
        st.rerun()


def _admin_listings() -> None:
    from oppos.sources.rfp_documents import start_reading
    rows = get_all_scored(0)
    unscored = [r for r in rows if (r.get("pipeline_status") or "new") in ("new", "qualified", "expiring_soon") and not _score_of(r)
                and r.get("source_id") not in PURSUED_IDS and not (_parse_json(r.get("stage1_json")) and not _parse_json(r.get("stage1_json")).get("relevant"))]
    if unscored and st.button(f"Score the {len(unscored)} open listings that have no fit score", key="adm_score_all"):
        _score_batch(unscored)
        st.rerun()
    q = st.text_input("Find a listing", key="adm_find", placeholder="Title, solicitation number or OppOS ID — any status")
    if not q.strip():
        st.caption(f"{len(rows):,} listings stored. Search to reopen, archive, re-read documents or re-score one.")
        return
    ql = q.strip().lower()
    hits = [r for r in rows if ql in (r.get("title") or "").lower() or ql in (r.get("solicitation_number") or "").lower()
            or ql == (r.get("source_id") or "").lower()][:30]
    if not hits:
        st.caption("No listing matches.")
        return
    pick = st.selectbox("Listing", hits, key="adm_listing", label_visibility="collapsed",
                        format_func=lambda r: f'{(r.get("title") or "")[:80]} · {PIPELINE_LABELS.get(r.get("pipeline_status") or "new", r.get("pipeline_status"))} · fit {int(_score_of(r))}')
    st.markdown(f'<div class="rmeta">{_row_meta(pick)} · ID {_esc(pick["source_id"])}</div>', unsafe_allow_html=True)
    with st.container(horizontal=True):
        status = pick.get("pipeline_status") or "new"
        if status in ("skipped", "expired", "lost") and pick["source_id"] not in OPEN_PURSUITS and st.button("Reopen", key="adm_l_reopen"):
            set_pipeline_status(pick["source_id"], "new", notes="Reopened by an admin")
            _flash("Reopened")
            st.rerun()
        if status in ("new", "qualified", "expiring_soon") and st.button("Archive", key="adm_l_archive"):
            set_pipeline_status(pick["source_id"], "skipped", notes="Archived by an admin")
            _flash("Archived")
            st.rerun()
        if st.button("Read its documents again", key="adm_l_read"):
            start_reading(pick)
            _flash("Reading its documents in the background", icon="📄")
            st.rerun()
        if st.button("Score it again", key="adm_l_score"):
            _score_one(pick, st.container())
            st.rerun()
        st.link_button("Open in OppOS", _app_link("desk" if pick["source_id"] in PURSUED_IDS else "", pick["source_id"]))


def _admin_portals() -> None:
    import pandas as pd
    from oppos.pursuits import REGISTRATION_STATUSES
    from oppos.storage.db import upsert_portal_registration
    cols = ["portal", "display_name", "status", "vendor_id", "login_owner", "lead_time_days", "url", "notes"]
    df = pd.DataFrame([{c: r.get(c) for c in cols} for r in PORTAL_REGS.values()], columns=cols).sort_values("display_name", na_position="last").reset_index(drop=True)
    df["lead_time_days"] = pd.to_numeric(df["lead_time_days"], errors="coerce")
    df["status"] = df["status"].fillna("unknown")
    known = sum(1 for s in df["status"] if s != "unknown")
    st.caption(f"Nutrient's accounts on procurement portals: {known} of {len(df)} known. Shown on every pursuit; never store passwords here.")
    edited = st.data_editor(df, hide_index=True, use_container_width=True, disabled=["portal", "display_name"], key="reg_editor",
                            column_config={
                                "portal": None,
                                "display_name": st.column_config.TextColumn("Portal"),
                                "status": st.column_config.SelectboxColumn("Our account", options=REGISTRATION_STATUSES, required=True),
                                "vendor_id": st.column_config.TextColumn("Vendor ID"),
                                "login_owner": st.column_config.TextColumn("Login held by"),
                                "lead_time_days": st.column_config.NumberColumn("Lead time (days)", min_value=0, step=1),
                                "url": st.column_config.LinkColumn("Registration page"),
                                "notes": st.column_config.TextColumn("Notes"),
                            })
    if st.button("Save portals", key="reg_save", type="primary"):
        clean = lambda v: None if v is None or (isinstance(v, float) and pd.isna(v)) else v
        changed = 0
        for new, old in zip(edited.to_dict("records"), df.to_dict("records")):
            n, o = {k: clean(v) for k, v in new.items()}, {k: clean(v) for k, v in old.items()}
            if n != o:
                lead = n.get("lead_time_days")
                upsert_portal_registration(n["portal"], status=n.get("status") or "unknown", vendor_id=n.get("vendor_id"),
                                           login_owner=n.get("login_owner"), lead_time_days=int(lead) if lead is not None else None,
                                           url=n.get("url"), notes=n.get("notes"))
                changed += 1
        _flash(f"Saved {changed} change{'s' if changed != 1 else ''}")
        st.rerun()


@st.cache_data(ttl=600, show_spinner=False)
def _nutrient_credits() -> dict | None:
    import httpx
    key = os.environ.get("NUTRIENT_API_KEY", "")
    if not key:
        return None
    try:
        r = httpx.get("https://api.nutrient.io/account/info", headers={"Authorization": f"Bearer {key}"}, timeout=10)
        return (r.json() or {}).get("usage") if r.status_code == 200 else None
    except Exception:
        return None


def _admin_system() -> None:
    from oppos.drafting import compliance_status as _compliance_status
    comp = _compliance_status()
    credits = _nutrient_credits()
    rows = []
    if credits:
        total, used = float(credits.get("totalCredits") or 0), float(credits.get("usedCredits") or 0)
        rows.append(("Nutrient API credits", f"{total - used:,.0f} left of {total:,.0f}"))
    else:
        rows.append(("Nutrient API credits", '<span class="alert">Unknown — NUTRIENT_API_KEY missing or rejected</span>'))
    rows += [
        ("Daily scan", f'Last scan {_ago(_cached_meta("last_scan"))} · <a href="https://github.com/brperdomo/OppOS/actions/workflows/scan.yml" target="_blank">runs on GitHub</a>'),
        ("Document editor licence", "set" if DOCAUTH_LICENSE_KEY else '<span class="alert">not set — Word/PDF exports carry an evaluation watermark</span>'),
        ("PDF viewer licence", "set" if VIEWER_LICENSE_KEY else '<span class="alert">not set — PDF preview carries a trial watermark</span>'),
        ("Security answers", f"approved v{_esc(str(comp['version']))} by {_esc(str(comp['approved_by']))} on {_esc(str(comp['approved_at']))}" if comp["approved"]
         else '<span class="alert">not approved — drafts mark security items [SECURITY TO CONFIRM] until oppos/drafting/compliance.md is approved</span>'),
        ("Slack", "connected" if os.environ.get("SLACK_WEBHOOK_URL") or os.environ.get("SLACK_BOT_TOKEN") else '<span class="alert">not configured</span>'),
        ("Notion", "connected" if os.environ.get("NOTION_TOKEN") else '<span class="alert">not configured</span>'),
    ]
    st.markdown('<div class="kvs">' + "".join(f'<div class="kv"><span>{l}</span><div>{v}</div></div>' for l, v in rows) + "</div>", unsafe_allow_html=True)
    with st.container(horizontal=True):
        if st.button("Send a test message to Slack", key="adm_slack"):
            from oppos.outputs import slack_pursuits as sp
            ok = sp._webhook({"text": f"OppOS test message from {CURRENT_USER['email']}"}) if os.environ.get("SLACK_WEBHOOK_URL") else \
                bool(sp.post(sp.SLACK_DIGEST_CHANNEL, f"OppOS test message from {CURRENT_USER['email']}")) if sp.bot_enabled() and sp.SLACK_DIGEST_CHANNEL else False
            _flash("Slack test sent" if ok else "Slack test failed — check the webhook or bot token", icon="✅" if ok else "⚠️")
            st.rerun()
        if st.button("Check the Notion connection", key="adm_notion"):
            try:
                from notion_client import Client
                Client(auth=os.environ.get("NOTION_TOKEN", "")).databases.retrieve(os.environ.get("NOTION_DATABASE_ID", ""))
                _flash("Notion connection works")
            except Exception as e:
                _flash(f"Notion check failed — {type(e).__name__}: {str(e)[:120]}", icon="⚠️")
            st.rerun()
    with st.expander("Secret names the app can see (for fixing a misplaced secret)"):
        try:
            names = [f"{k} (section: {', '.join(sorted(v.keys()))})" if hasattr(v, "keys") else k for k, v in ((k, st.secrets[k]) for k in sorted(st.secrets.keys()))]
            seen = ", ".join(names) or "none"
        except Exception as e:
            seen = f"no secrets file ({type(e).__name__})"
        st.caption(f"{seen}. The editor reads DOCAUTH_LICENSE_KEY and VIEWER_LICENSE_KEY at the top level, outside any [section]. Values are never shown.")



_PAGE_POOL = st.Page(page_pool, title="Find RFPs", icon=":material/search:", default=True)  # served at /
_PAGE_DESK = st.Page(page_desk, title="My desk", icon=":material/person:", url_path="desk")
_PAGE_ADMIN = st.Page(page_admin, title="Admin", icon=":material/settings:", url_path="admin")
_nav = st.navigation(
    [_PAGE_POOL, _PAGE_DESK, _PAGE_ADMIN],
    position="top",
)
_nav.run()
