"""OppOS Streamlit dashboard.

Run with:
    streamlit run oppos/dashboard/app.py
"""

from __future__ import annotations

import json
import logging
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
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

:root {
    --bg-primary: #1a1414;
    --bg-secondary: #231e1e;
    --bg-tertiary: #302b2b;
    --bg-card: #231e1e;
    --text-primary: #efebe7;
    --text-secondary: #c2b8ae;
    --text-tertiary: #897e70;
    --accent-gold: #f0c966;
    --accent-green: #6eb479;
    --accent-red: #f25f45;
    --accent-pink: #de9dcc;
    --accent-orange: #e8944c;
    --border-subtle: rgba(104, 89, 75, 0.3);
    --border-medium: rgba(104, 89, 75, 0.6);
    --radius-sm: 8px;
    --radius-md: 12px;
    --radius-lg: 16px;
}

.stApp {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
}

/* Hide Streamlit chrome — but keep the header: it hosts the page navigation */
#MainMenu, footer {visibility: hidden;}
/* Reruns: keep the previous frame fully visible while the next one renders (no grey fade), and hide the
   "running" status widget that flickers on every click. Real long operations still use st.spinner/st.status. */
.stApp [data-stale="true"], .element-container[data-stale="true"], [data-stale="true"] { opacity: 1 !important; transition: none !important; }
[data-testid="stStatusWidget"] { visibility: hidden !important; }
.stDeployButton, [data-testid="stAppDeployButton"], [data-testid="stToolbarActions"] {display: none;}
header[data-testid="stHeader"] { background: var(--bg-primary); }  /* opaque: content scrolls under it */
header[data-testid="stHeader"] a, header[data-testid="stHeader"] span { font-size: 14px; }

/* Main container */
.block-container {
    padding-top: 2rem !important;
    max-width: 1200px !important;
}

/* Custom header */
.oppos-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 6px 0 4px 0;
    margin-bottom: 4px;
}
.who { font-size: 12px; color: var(--text-tertiary); text-align: right; }
.welcome { font-size: 14px; line-height: 1.55; color: var(--text-secondary); }
.welcome-title { font-size: 16px; font-weight: 600; color: var(--text-primary); margin-bottom: 6px; }
.welcome ol { margin: 0 0 8px 18px; padding: 0; }
.welcome li { margin: 4px 0; }
.welcome b { color: var(--text-primary); font-weight: 600; }
.welcome-note { font-size: 12px; color: var(--text-tertiary); }
.pp-in-card { margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--border-subtle); }
.pp-next { margin-top: 6px; font-size: 13px; color: var(--text-primary); }
.pp-next::before { content: '→ '; color: var(--accent-gold); }
.desk-section { margin: 18px 0 6px; font-size: 12px; letter-spacing: .02em; color: var(--text-tertiary); }
.desk-section span { margin-left: 8px; color: var(--text-tertiary); opacity: .8; }
.desk-row { padding: 8px 12px; border-left: 3px solid transparent; }
.desk-row.sel { border-left-color: var(--accent-gold); background: rgba(240, 201, 102, 0.06); border-radius: 0 var(--radius-sm) var(--radius-sm) 0; }
.desk-title { font-size: 15px; font-weight: 600; color: var(--text-primary); }
.desk-sub { font-size: 12px; color: var(--text-tertiary); margin-top: 2px; }
.desk-sub .desk-warn { color: var(--accent-orange); }
.desk-sub .desk-bad { color: var(--accent-red); }
.desk-meta { font-size: 12px; color: var(--text-secondary); text-align: right; }
.desk-meta .opp-tag { margin-left: 6px; }
.desk-workspace { margin-top: 22px; border-top: 1px solid var(--border-medium); padding-top: 14px; }
.sub-box { margin-top: 12px; padding: 10px 12px; border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); background: rgba(255,255,255,0.025); font-size: 13px; line-height: 1.7; color: var(--text-secondary); }
.sub-title { font-size: 12px; font-weight: 600; color: var(--text-primary); margin-bottom: 2px; }
.sub-k { display: inline-block; min-width: 56px; color: var(--text-tertiary); font-size: 12px; }
.sub-ok { color: var(--accent-green); } .sub-warn { color: var(--accent-orange); } .sub-bad { color: var(--accent-red); }
.sub-src { color: var(--text-tertiary); font-size: 12px; }
.sub-missing { margin-top: 4px; color: var(--accent-orange); font-size: 12px; }
.sub-box a { color: var(--accent-gold); text-decoration: none; }
.oppos-header-left {
    display: flex;
    align-items: center;
    gap: 16px;
}
.oppos-header h1 {
    font-family: 'Inter', sans-serif;
    font-size: 26px;
    font-weight: 700;
    color: var(--text-primary);
    margin: 0;
    letter-spacing: -0.5px;
}
.oppos-header .subtitle {
    font-size: 13px;
    color: var(--text-tertiary);
    font-weight: 400;
}
.nutrient-logo-mark {
    display: flex;
    align-items: center;
    gap: 10px;
}
.nutrient-logo-mark svg {
    width: 32px;
    height: 32px;
}
.nutrient-brand {
    display: flex;
    align-items: center;
    gap: 8px;
    color: var(--text-tertiary);
    font-size: 12px;
    font-weight: 500;
    letter-spacing: 0.3px;
}
.nutrient-brand svg {
    height: 16px;
    width: auto;
    opacity: 0.7;
}
.nutrient-brand:hover svg {
    opacity: 1;
}

/* Footer */
.oppos-footer {
    text-align: center;
    padding: 32px 0 16px 0;
    margin-top: 48px;
    border-top: 1px solid var(--border-subtle);
    color: var(--text-tertiary);
    font-size: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
}
.oppos-footer svg {
    height: 14px;
    width: auto;
    opacity: 0.5;
}

/* Stats bar */
.stats-bar {
    display: flex;
    gap: 24px;
    padding: 16px 24px;
    background: var(--bg-secondary);
    border-radius: var(--radius-md);
    border: 1px solid var(--border-subtle);
    border-top: 2px solid var(--accent-gold);
    margin-bottom: 24px;
}
.stat-item {
    display: flex;
    flex-direction: column;
    gap: 2px;
}
.stat-value {
    font-size: 24px;
    font-weight: 700;
    color: var(--text-primary);
}
.stat-value.gold { color: var(--accent-gold); }
.stat-value.green { color: var(--accent-green); }
.stat-value.pink { color: var(--accent-pink); }
.stat-label {
    font-size: 12px;
    font-weight: 500;
    color: var(--text-tertiary);
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

/* Opportunity cards */
.opp-card {
    background: var(--bg-secondary);
    border: 1px solid var(--border-subtle);
    border-left: 4px solid var(--text-tertiary);
    border-radius: var(--radius-md);
    padding: 20px 24px;
    margin-bottom: 24px;
    transition: border-color 0.2s ease, box-shadow 0.2s ease;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}
.opp-card:hover {
    border-color: var(--border-medium);
    box-shadow: 0 2px 8px rgba(0,0,0,0.15);
}
.opp-card.score-high-card { border-left-color: var(--accent-green); }
.opp-card.score-mid-card { border-left-color: var(--accent-gold); }
.opp-card.score-low-card { border-left-color: var(--text-tertiary); }
.opp-card-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 16px;
    margin-bottom: 12px;
}
.opp-title {
    font-size: 17px;
    font-weight: 600;
    color: var(--text-primary);
    text-decoration: none;
    line-height: 1.35;
}
.opp-title:hover {
    color: var(--accent-gold);
}
a.opp-title { color: var(--text-primary); text-decoration: none; }
a.opp-title:hover { color: var(--accent-gold); }
.opp-subtitle {
    font-size: 13px;
    color: var(--text-secondary);
    margin-top: 4px;
    line-height: 1.4;
}

.opp-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 8px;
}
.opp-tag {
    display: inline-flex;
    align-items: center;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 500;
    border: none;
    color: var(--text-secondary);
    background: var(--bg-tertiary);
}
.opp-tag.source {
    background: rgba(222, 157, 204, 0.1);
    color: var(--accent-pink);
}
.opp-tag.deadline {
    background: rgba(240, 201, 102, 0.1);
    color: var(--accent-gold);
}

/* Score badge */
.score-badge {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-width: 64px;
    height: 64px;
    border-radius: var(--radius-md);
    background: var(--bg-tertiary);
    border: none;
    flex-shrink: 0;
}
.score-number {
    font-size: 26px;
    font-weight: 700;
    line-height: 1;
}
.score-label {
    font-size: 9px;
    font-weight: 600;
    color: var(--text-tertiary);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-top: 2px;
}
.score-high .score-number { color: var(--accent-green); }
.score-mid .score-number { color: var(--accent-gold); }
.score-low .score-number { color: var(--text-tertiary); }

/* AI summary line */
.opp-summary {
    font-size: 13px;
    color: var(--text-secondary);
    line-height: 1.5;
    margin-top: 8px;
    padding-top: 10px;
    border-top: 1px solid var(--border-subtle);
    font-style: italic;
}

/* Detail grid */
.detail-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 12px;
    margin-top: 12px;
    padding-top: 12px;
    border-top: 1px solid var(--border-subtle);
}
.detail-item {
    display: flex;
    flex-direction: column;
    gap: 2px;
}
.detail-label {
    font-size: 11px;
    font-weight: 500;
    color: var(--text-tertiary);
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.detail-value {
    font-size: 14px;
    color: var(--text-secondary);
    font-weight: 400;
}
.detail-value a {
    color: var(--accent-gold);
    text-decoration: none;
}
.detail-value a:hover {
    text-decoration: underline;
}

/* Expander overrides */
.streamlit-expanderHeader {
    font-family: 'Inter', sans-serif !important;
    font-size: 13px !important;
    font-weight: 600 !important;
    color: var(--text-secondary) !important;
    background: var(--bg-tertiary) !important;
    border-radius: var(--radius-sm) !important;
    border: 1px solid var(--border-subtle) !important;
}
div[data-testid="stExpander"] {
    border: 1px solid var(--border-subtle) !important;
    border-radius: var(--radius-sm) !important;
    background: var(--bg-tertiary) !important;
}
div[data-testid="stExpander"] details {
    border: none !important;
}

/* Assessment section */
.assessment-section {
    padding: 16px;
    background: var(--bg-tertiary);
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-subtle);
    margin-top: 8px;
}
.assessment-summary {
    font-size: 14px;
    line-height: 1.6;
    color: var(--text-secondary);
    margin-bottom: 16px;
}
.strength-item {
    color: var(--accent-green);
    font-size: 13px;
    padding: 4px 0;
}
.risk-item {
    color: var(--accent-red);
    font-size: 13px;
    padding: 4px 0;
}

/* Filter bar */
div[data-testid="stHorizontalBlock"] {
    gap: 12px !important;
}

/* Slider overrides */
div[data-testid="stSlider"] label {
    font-size: 13px !important;
    font-weight: 500 !important;
    color: var(--text-tertiary) !important;
}

/* Multiselect overrides */
div[data-testid="stMultiSelect"] label,
div[data-testid="stSelectbox"] label {
    font-size: 13px !important;
    font-weight: 500 !important;
    color: var(--text-tertiary) !important;
}

/* Download button */
div[data-testid="stDownloadButton"] button {
    background: var(--bg-tertiary) !important;
    border: 1px solid var(--border-subtle) !important;
    color: var(--accent-gold) !important;
    font-size: 12px !important;
    border-radius: var(--radius-sm) !important;
    transition: all 0.2s ease;
}
div[data-testid="stDownloadButton"] button:hover {
    border-color: var(--accent-gold) !important;
    background: rgba(240, 201, 102, 0.1) !important;
}

/* Divider */
hr {
    border-color: var(--border-subtle) !important;
    margin: 8px 0 !important;
}

/* Source health */
.health-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.health-table th { text-align: left; color: var(--text-tertiary); font-weight: 500; font-size: 11px;
    text-transform: uppercase; letter-spacing: .04em; padding: 6px 8px; border-bottom: 1px solid var(--border-subtle); }
.health-table td { padding: 6px 8px; border-bottom: 1px solid var(--border-subtle); color: var(--text-secondary); vertical-align: top; }
.health-note { color: var(--text-tertiary); font-size: 12px; }

/* LOB chip, evidence, unknowns */
.opp-tag.lob-tag { border: 1px solid var(--accent-gold); color: var(--accent-gold); background: transparent; }
.evidence-quote { color: var(--text-tertiary); font-size: 12px; font-style: italic; margin: 2px 0 6px 14px; }
.gap-item { color: var(--text-secondary); font-size: 13px; padding: 2px 0; }

/* Registration badge + pursuit panel */
.reg-badge { font-size: 11px; padding: 2px 8px; border-radius: 10px; margin-left: 6px; border: 1px solid currentColor; }
.reg-ok { color: #7fc29b; }
.reg-warn { color: var(--accent-orange); }
.reg-bad { color: var(--accent-red); }
.pp-strip { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin: 2px 0 10px; font-size: 13px; color: var(--text-secondary); }
.pp-owner { font-weight: 500; color: var(--text-primary, #efebe7); }
.pp-pill { padding: 2px 10px; border-radius: 10px; border: 1px solid var(--border-subtle); color: var(--text-secondary); font-size: 12px; }
.pp-ok { border-color: #7fc29b; color: #7fc29b; }
.pp-warn { border-color: var(--accent-orange); color: var(--accent-orange); }
.pp-bad { border-color: var(--accent-red); color: var(--accent-red); }
.pp-links { margin-left: auto; font-size: 12px; }
.pp-links a { color: var(--accent-gold); text-decoration: none; margin-left: 8px; }
.pp-event { font-size: 12px; color: var(--text-tertiary); padding: 2px 0; }
.pp-event b { color: var(--text-secondary); font-weight: 500; }

/* Owner chip */
.opp-tag.owner-tag { background: rgba(240, 201, 102, 0.12); color: var(--accent-gold); }
.board-link a { color: var(--text-primary, #efebe7); text-decoration: none; }
.board-link a:hover { color: var(--accent-gold); }

/* Empty state */
.empty-state {
    text-align: center;
    padding: 48px 24px;
    color: var(--text-tertiary);
    background: var(--bg-secondary);
    border: 1px dashed var(--border-subtle);
    border-radius: var(--radius-md);
}
.empty-state h3 {
    color: var(--text-secondary);
    font-weight: 500;
    font-size: 14px;
    margin-bottom: 0;
    line-height: 1.5;
}

/* Contact section */
.contact-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 4px 0;
    font-size: 14px;
    color: var(--text-secondary);
}
.contact-row a {
    color: var(--accent-gold);
    text-decoration: none;
}

/* Pipeline status badges */
.pipeline-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 3px 10px;
    border-radius: 100px;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.pipeline-new {
    background: rgba(222, 157, 204, 0.15);
    color: var(--accent-pink);
    border: 1px solid rgba(222, 157, 204, 0.3);
}
.pipeline-qualified {
    background: rgba(100, 160, 240, 0.15);
    color: #64a0f0;
    border: 1px solid rgba(100, 160, 240, 0.3);
}
.pipeline-in_progress {
    background: rgba(240, 201, 102, 0.15);
    color: var(--accent-gold);
    border: 1px solid rgba(240, 201, 102, 0.3);
}
.pipeline-submitted {
    background: rgba(110, 180, 121, 0.15);
    color: var(--accent-green);
    border: 1px solid rgba(110, 180, 121, 0.3);
}
.pipeline-won {
    background: rgba(110, 180, 121, 0.3);
    color: var(--accent-green);
    border: 1px solid rgba(110, 180, 121, 0.5);
}
.pipeline-lost {
    background: rgba(242, 95, 69, 0.15);
    color: var(--accent-red);
    border: 1px solid rgba(242, 95, 69, 0.3);
}
.pipeline-skipped {
    background: rgba(137, 126, 112, 0.1);
    color: var(--text-tertiary);
    border: 1px solid rgba(137, 126, 112, 0.2);
}
.pipeline-expiring_soon {
    background: rgba(232, 148, 76, 0.2);
    color: var(--accent-orange);
    border: 1px solid rgba(232, 148, 76, 0.4);
    animation: pulse-warning 2s ease-in-out infinite;
}
.pipeline-expired {
    background: rgba(242, 95, 69, 0.15);
    color: var(--accent-red);
    border: 1px solid rgba(242, 95, 69, 0.3);
    text-decoration: line-through;
}
@keyframes pulse-warning {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.7; }
}
.opp-tag.deadline-urgent {
    background: rgba(232, 148, 76, 0.2);
    color: var(--accent-orange);
    font-weight: 600;
}
.opp-tag.deadline-expired {
    background: rgba(242, 95, 69, 0.15);
    color: var(--accent-red);
    text-decoration: line-through;
}

/* NEW badge */
.new-badge {
    display: inline-flex;
    align-items: center;
    padding: 2px 8px;
    border-radius: 100px;
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    background: rgba(242, 95, 69, 0.2);
    color: var(--accent-red);
    border: 1px solid rgba(242, 95, 69, 0.4);
    animation: pulse-new 2s ease-in-out infinite;
}
@keyframes pulse-new {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.6; }
}

/* Scan button */
div[data-testid="stButton"] > button.scan-btn {
    background: linear-gradient(135deg, var(--accent-gold), #e0b44e) !important;
    color: var(--bg-primary) !important;
    font-weight: 700 !important;
    font-size: 14px !important;
    border: none !important;
    border-radius: var(--radius-sm) !important;
    padding: 10px 24px !important;
    letter-spacing: 0.3px;
    transition: all 0.2s ease;
}
div[data-testid="stButton"] > button.scan-btn:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(240, 201, 102, 0.3) !important;
}
.scan-result {
    padding: 16px 24px;
    background: rgba(110, 180, 121, 0.1);
    border: 1px solid rgba(110, 180, 121, 0.3);
    border-radius: var(--radius-md);
    margin-bottom: 16px;
    color: var(--accent-green);
    font-size: 14px;
    font-weight: 500;
}
.scan-result.no-new {
    background: rgba(137, 126, 112, 0.1);
    border-color: rgba(137, 126, 112, 0.3);
    color: var(--text-secondary);
}
.last-scan {
    font-size: 12px;
    color: var(--text-tertiary);
    margin-top: 4px;
}

/* Streamlit tabs override */
div[data-testid="stTabs"] button[data-baseweb="tab"] {
    font-family: 'Inter', sans-serif !important;
    font-size: 14px !important;
    font-weight: 600 !important;
    padding: 10px 20px !important;
}
div[data-testid="stTabs"] [data-baseweb="tab-highlight"] {
    background-color: var(--accent-gold) !important;
}
/* Quieter controls: one action row per item, folds instead of stacked panels */
[data-testid="stExpander"] details { border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); background: transparent; }
[data-testid="stExpander"] summary { font-size: 13px; color: var(--text-secondary); padding: 6px 12px; }
[data-testid="stExpander"] summary:hover { color: var(--text-primary); }
.stButton > button, [data-testid="stPopover"] > button { font-size: 13px; padding: 4px 12px; min-height: 34px; border-radius: var(--radius-sm); }
.stButton > button[kind="secondary"], [data-testid="stPopover"] > button { border-color: var(--border-medium); }
[data-testid="stCaptionContainer"] { font-size: 12px; }
.opp-card { margin-bottom: 8px; }
hr { margin: 14px 0 !important; opacity: 0.5; }
[data-testid="stTabs"] [data-baseweb="tab"] { font-size: 14px; }
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

_hc1, _hc2, _hc3, _hc4 = st.columns([4, 2.4, 1, 1], vertical_alignment="center")
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


def _welcome() -> None:
    """Three-step orientation, shown until the signed-in person dismisses it; "How it works" brings it back."""
    key = f"welcome_seen:{CURRENT_USER.get('email', '')}"
    if not st.session_state.get("show_welcome") and _cached_meta(key):
        return
    with st.container(border=True):
        st.markdown(
            '<div class="welcome">'
            '<div class="welcome-title">Three steps from an RFP to a submitted response</div>'
            '<ol>'
            '<li><b>Find RFPs</b> is everything our scanner found at public portals that nobody has taken yet, scored for fit '
            '(how well it matches what Nutrient sells, 0 to 100; 65 and up is worth a look). Use <b>Grab</b> on anything you want to evaluate. '
            'Got one from elsewhere? <b>Add an RFP</b> takes a link, a file, or just what you know.</li>'
            '<li>Grabbed RFPs sit on <b>My desk</b>. Decide: <b>Start pursuing</b> opens a Notion page and a Slack channel and starts reminders, '
            'or <b>Put it back</b> for someone else.</li>'
            '<li>For a pursuit, <b>Draft response</b> writes a first answer to every requirement; open the document, review the marked spots, '
            'download it as Word or PDF, submit it on the portal, then <b>Mark submitted</b> and later record Won or Lost.</li>'
            '</ol>'
            '<div class="welcome-note">Every click confirms itself in the corner, and the team sees each step in Slack. '
            'The Team view on My desk shows what everyone else is working on.</div></div>',
            unsafe_allow_html=True,
        )
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


def _ensure_files_exist(opp: dict, selected_paths: list) -> list:
    """Verify selected files exist on disk; re-download if missing."""
    from oppos.sources.attachments import download_attachments

    missing = [f for f in selected_paths if not f.exists()]
    if not missing:
        return selected_paths

    # Re-download all attachments for this RFP, then map back to selected
    raw_json = opp.get("raw_json") or "{}"
    try:
        raw = json.loads(raw_json) if isinstance(raw_json, str) else (raw_json or {})
    except (json.JSONDecodeError, TypeError):
        raw = {}

    # Reconstruct opp dict with fields that download_attachments needs
    download_opp = dict(opp)
    if raw.get("resourceLinks"):
        download_opp["resource_links"] = raw["resourceLinks"]

    redownloaded = download_attachments(download_opp)
    if not redownloaded:
        return selected_paths  # return originals — caller will handle missing files

    # Build a name → path map from freshly downloaded files
    fresh_map = {f.name: f for f in redownloaded}

    # Update session state with new paths
    sid = opp.get("source_id", "")
    state_key = f"att_files_{sid}"
    st.session_state[state_key] = [str(f) for f in redownloaded]

    # Map selected files to fresh paths
    refreshed = []
    for f in selected_paths:
        if f.name in fresh_map:
            refreshed.append(fresh_map[f.name])
        elif f.exists():
            refreshed.append(f)
    return refreshed


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


def _run_ocr_and_score(opp: dict, selected_paths: list, tab_key: str) -> None:
    """Extract text from selected files, merge with existing, re-score, and move to Qualified."""
    from oppos.scoring.qualifier import qualify
    from oppos.sources.extract_text import extract_file, MAX_TOTAL_TEXT
    from oppos.storage.db import upsert_opportunity

    old_score = int(opp.get("fit_score") or 0)
    title = opp.get("title", "Untitled")
    existing_text = opp.get("attachment_text") or ""

    with st.status(f"Scanning: {title[:60]}", expanded=True) as status:
        # Verify files exist on disk; re-download if Streamlit Cloud cleaned them up
        missing = [f for f in selected_paths if not f.exists()]
        if missing:
            st.write(f"⚠️ {len(missing)} file(s) not found on disk — re-downloading...")
            selected_paths = _ensure_files_exist(opp, selected_paths)

        # Check again after re-download attempt
        still_missing = [f for f in selected_paths if not f.exists()]
        if still_missing:
            for f in still_missing:
                st.write(f"  ❌ {f.name} — file not found (could not re-download)")
            selected_paths = [f for f in selected_paths if f.exists()]
            if not selected_paths:
                status.update(label="Scan failed: All files missing", state="error")
                st.error("Files were cleaned up and could not be re-downloaded. Try clicking 'Load Attachments' again.")
                return

        pdf_count = sum(1 for f in selected_paths if f.suffix.lower() == ".pdf")
        docx_count = sum(1 for f in selected_paths if f.suffix.lower() == ".docx")
        parts = []
        if pdf_count:
            parts.append(f"{pdf_count} PDF(s) via Nutrient OCR")
        if docx_count:
            parts.append(f"{docx_count} DOCX (local, no credits)")
        st.write(f"🔍 **Extracting text from {' + '.join(parts)}...**")

        all_text = []
        total_chars = 0

        for i, file_path in enumerate(selected_paths):
            if total_chars >= MAX_TOTAL_TEXT:
                st.write(f"  ⏭️ {file_path.name} — skipped (text limit reached)")
                continue

            is_docx = file_path.suffix.lower() == ".docx"
            method = "local parse" if is_docx else "Nutrient OCR"
            st.write(f"  ⏳ ({i+1}/{len(selected_paths)}) Processing **{file_path.name}** ({method})...")
            result = extract_file(file_path)

            if result.get("error"):
                st.write(f"  ❌ {file_path.name} — {result['error']}")
                continue

            credits = result.get("credits_remaining", "n/a")
            credit_info = "" if is_docx else f" (credits left: {credits})"
            pages_info = f"{result['pages']} pages," if result['pages'] else ""
            st.write(
                f"  ✅ {file_path.name} — {result['chars']:,} chars "
                f"{pages_info}{credit_info}"
            )

            if result["text"]:
                all_text.append(f"--- {file_path.name} ---\n{result['text']}")
                total_chars += result["chars"]

        new_text = "\n\n".join(all_text)

        if not new_text:
            status.update(label="Scan failed: Could not extract text", state="error")
            return

        if existing_text:
            combined_text = (existing_text + "\n\n" + new_text)[:MAX_TOTAL_TEXT]
            st.write(f"📎 Merged with previously scanned text ({len(existing_text):,} chars existing)")
        else:
            combined_text = new_text[:MAX_TOTAL_TEXT]

        st.divider()
        st.write(f"🧠 **Total context: {len(combined_text):,} chars** — Scoring with Claude...")

        try:
            scored = qualify(opp, attachment_text=combined_text)
            scored["attachment_text"] = combined_text
            upsert_opportunity(scored)
            # Keep expiring_soon status if already set — don't reset to qualified
            _current_status = opp.get("pipeline_status") or "new"
            _post_scan_status = _current_status if _current_status == "expiring_soon" else "qualified"
            set_pipeline_status(
                opp["source_id"], _post_scan_status,
                notes=f"Deep scan: {len(combined_text):,} chars from {len(selected_paths)} file(s)",
            )
        except Exception as e:
            status.update(label="Scan failed: Scoring error", state="error")
            st.error(f"Scoring failed: {type(e).__name__}: {e}")
            # Save OCR text even if scoring fails so credits aren't wasted
            opp["attachment_text"] = combined_text
            upsert_opportunity(opp)
            st.write("💾 OCR text saved — you can re-score later without using credits.")
            return

        new_score = scored.get("fit_score", 0)
        delta = new_score - old_score
        delta_str = f"+{delta}" if delta > 0 else str(delta)

        st.write(f"**Score: {old_score} → {new_score} ({delta_str})**")

        s2 = scored.get("stage2") or {}
        if s2.get("summary"):
            st.divider()
            st.write("📋 **Post-Scan Analysis**")
            st.write(s2["summary"])
        if s2.get("strengths"):
            st.write("**Strengths:** " + points_text(s2["strengths"]))
        if s2.get("risks"):
            st.write("**Risks:** " + points_text(s2["risks"]))
        if s2.get("recommended_action"):
            st.write(f"**Recommendation:** {s2['recommended_action']}")

        if _post_scan_status == "expiring_soon":
            st.write("⚠️ **Scored — stays in Expiring Soon (deadline approaching).**")
        else:
            st.write("📂 **Moved to Qualified tab for review.**")

        status.update(
            label=f"Scan complete — Score: {old_score} → {new_score} ({delta_str})",
            state="complete",
        )


def _get_scanned_filenames(attachment_text: str) -> set[str]:
    """Parse '--- filename ---' headers from cached attachment text."""
    import re
    return set(re.findall(r"^--- (.+?) ---$", attachment_text, re.MULTILINE))


def _render_deep_scan(opp: dict, tab_key: str, slot=None) -> None:
    """Render the Deep Scan UI: load attachments, select files, scan & score."""
    from oppos.sources.attachments import download_attachments
    from pathlib import Path

    sid = opp.get("source_id", "")
    state_key = f"att_files_{sid}"
    existing_text = opp.get("attachment_text") or ""
    scanned_files = _get_scanned_filenames(existing_text) if existing_text else set()

    if scanned_files:
        _scan_score = int(opp.get("fit_score") or 0)
        st.markdown(
            f'<div style="font-size: 12px; color: var(--accent-green); margin-bottom: 4px;">'
            f'✅ {len(scanned_files)} file(s) scanned — current score: <strong>{_scan_score}/100</strong></div>',
            unsafe_allow_html=True,
        )

    # Step 1: Load Attachments
    lc1, lc2 = st.columns([1, 3])
    with lc1:
        load_btn = st.button(
            "Load Attachments",
            key=f"loadatt_{tab_key}_{sid}",
            use_container_width=True,
        )
    with lc2:
        st.caption("Downloads the RFP documents so they can be scanned (Nutrient OCR) and the fit re-scored on the full text.")

    if load_btn:
        with st.spinner("Downloading attachments..."):
            # Reconstruct resource_links from raw_json if not present
            # (DB rows don't store resource_links as a top-level field)
            download_opp = dict(opp)
            if not download_opp.get("resource_links"):
                raw_json = opp.get("raw_json") or "{}"
                try:
                    raw = json.loads(raw_json) if isinstance(raw_json, str) else (raw_json or {})
                except (json.JSONDecodeError, TypeError):
                    raw = {}
                if raw.get("resourceLinks"):
                    download_opp["resource_links"] = raw["resourceLinks"]
            att_files = download_attachments(download_opp)
        if att_files:
            st.session_state[state_key] = [str(f) for f in att_files]
        else:
            st.warning("No attachments found for this RFP.")
            return

    # Step 2: Show file list with checkboxes
    if state_key in st.session_state:
        from oppos.sources.extract_text import SCANNABLE_EXTENSIONS

        def _pdf_page_count(fpath: Path) -> int | None:
            try:
                from pypdf import PdfReader
                return len(PdfReader(str(fpath)).pages)
            except Exception:
                return None

        def _format_size(size_bytes: int) -> str:
            if size_bytes >= 1_048_576:
                return f"{size_bytes / 1_048_576:.1f} MB"
            return f"{size_bytes / 1024:.0f} KB"

        att_files = [Path(p) for p in st.session_state[state_key]]
        scannable = [f for f in att_files if f.suffix.lower() in SCANNABLE_EXTENSIONS]
        other = [f for f in att_files if f.suffix.lower() not in SCANNABLE_EXTENSIONS]

        pdf_count = sum(1 for f in scannable if f.suffix.lower() == ".pdf")
        docx_count = sum(1 for f in scannable if f.suffix.lower() == ".docx")
        type_parts = []
        if pdf_count:
            type_parts.append(f"{pdf_count} PDFs")
        if docx_count:
            type_parts.append(f"{docx_count} DOCX")
        st.markdown(
            f'<div style="font-size: 13px; margin: 8px 0 4px 0;">'
            f'<strong>{len(att_files)} files</strong> ({", ".join(type_parts)}, {len(other)} other)</div>',
            unsafe_allow_html=True,
        )

        selected = []
        for f in att_files:
            ext = f.suffix.lower()
            is_scannable = ext in SCANNABLE_EXTENSIONS
            already_scanned = f.name in scanned_files
            size_bytes = f.stat().st_size if f.exists() else 0
            size_str = _format_size(size_bytes)

            if ext == ".pdf":
                icon, method = "📄", "Nutrient OCR"
                pages = _pdf_page_count(f)
                page_str = f", {pages} pg" if pages else ""
            elif ext == ".docx":
                icon, method = "📝", "local parse, no credits"
                page_str = ""
            else:
                icon, method = "📎", ""
                page_str = ""

            label = f"{icon} {f.name} ({size_str}{page_str})"

            if already_scanned:
                st.markdown(
                    f'<div style="font-size: 13px; color: var(--accent-green); padding: 4px 0 4px 24px;">'
                    f'✅ {label} — already scanned</div>',
                    unsafe_allow_html=True,
                )
            elif is_scannable:
                hint = f" — {method}" if method else ""
                checked = st.checkbox(f"{label}{hint}", value=True, key=f"cb_{tab_key}_{sid}_{f.name}")
                if checked:
                    selected.append(f)
            else:
                st.markdown(
                    f'<div style="font-size: 12px; color: var(--text-tertiary); padding: 2px 0 2px 24px;">'
                    f'{label} (not scannable)</div>',
                    unsafe_allow_html=True,
                )

        if selected:
            scan_btn = st.button(
                f"Scan {len(selected)} Selected & Score",
                key=f"scansel_{tab_key}_{sid}",
                use_container_width=False,
            )
            if scan_btn:
                with (slot or st.container()):
                    _run_ocr_and_score(opp, selected, tab_key)
                _flash(f"Scanned and scored — {opp.get('title', '')[:60]}", icon="📊")
                st.rerun()
        elif scannable and not any(f.name not in scanned_files for f in scannable):
            _rescore_col1, _rescore_col2 = st.columns([1, 3])
            with _rescore_col1:
                if st.button("Re-Score", key=f"rescore_{tab_key}_{sid}", use_container_width=True):
                    with (slot or st.container()):
                        _run_ocr_and_score(opp, scannable, tab_key)
                    _flash(f"Re-scored — {opp.get('title', '')[:60]}", icon="📊")
                    st.rerun()
            with _rescore_col2:
                st.markdown(
                    '<div style="font-size: 12px; color: var(--text-tertiary); padding-top: 8px;">'
                    'All files scanned — re-score with existing text to update fit score</div>',
                    unsafe_allow_html=True,
                )


def _evidence_html(point) -> str:
    ev = point_evidence(point)
    return f'<div class="evidence-quote">“{_esc(ev)}”</div>' if ev else ""


def _app_link(page: str, sid: str) -> str:
    """Address of one listing (page "") or pursuit (page "desk") in this app; relative when OPPOS_APP_URL is unset."""
    base = (os.environ.get("OPPOS_APP_URL") or "").rstrip("/")
    return f"{base}/{page}?open={sid}" if page else f"{base}/?open={sid}"


def _deadline_tag(deadline: str | None) -> tuple[str, str]:
    """(css class, label) for the deadline pill."""
    if not deadline:
        return "deadline", "No deadline"
    from oppos.storage.db import _parse_deadline
    dl = _parse_deadline(deadline)
    if not dl:
        return "deadline", f"Due {deadline[:10]}"
    if dl.tzinfo is not None:
        dl = dl.replace(tzinfo=None)
    days = (dl - datetime.utcnow()).total_seconds() / 86400
    if days < 0:
        return "deadline-expired", f"Expired {deadline[:10]}"
    if days <= 7:
        return "deadline-urgent", f"Due in {max(0, int(days))}d · {deadline[:10]}"
    return "deadline", f"Due {deadline[:10]}"


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


def render_card(opp: dict, tab_key: str, mode: str = "pool", extra_meta_html: str = "", before_details=None, details: bool = True):
    """One opportunity. `mode`: 'pool' (Find RFPs — Grab / Skip / Score actions), 'desk' (actions live in the
    pursuit panel), 'archive' (closed — Reopen only)."""
    s2 = _parse_json(opp.get("stage2_json"))
    sid = opp.get("source_id", "")
    score = int(_score_of(opp))
    title = _esc(opp.get("title") or "Untitled")
    agency = _esc(opp.get("agency") or "Unknown agency")
    url = opp.get("url") or ""
    pipeline_status = opp.get("pipeline_status") or "new"
    state_name = _esc(SOURCE_STATE_MAP.get(opp.get("source", ""), "") or SOURCE_LABELS.get(opp.get("source", ""), ""))

    dl_cls, dl_txt = _deadline_tag(opp.get("response_deadline"))
    tags = [] if mode == "desk" else [f'<span class="opp-tag {dl_cls}">{_esc(dl_txt)}</span>']  # the desk strip carries the due date
    _lob_key = opp.get("lob") or s2.get("lob") or ""
    if _lob_key:
        tags.append(f'<span class="opp-tag lob-tag">{_esc(lob_label(_lob_key))}</span>')
    if opp.get("attachment_text"):
        tags.append('<span class="opp-tag">Docs scanned</span>')
    if opp.get("solicitation_number"):
        tags.append(f'<span class="opp-tag">{_esc(opp["solicitation_number"])}</span>')
    if mode == "archive" or pipeline_status in ("won", "lost", "skipped", "expired"):
        tags.insert(0, f'<span class="pipeline-badge pipeline-{pipeline_status}">{PIPELINE_LABELS.get(pipeline_status, pipeline_status)}</span>')
    _badge = _reg_badge(PORTAL_REGS.get(opp.get("source") or ""))
    if _badge and _badge[1] != "reg-ok" and mode != "desk":
        tags.append(f'<span class="reg-badge {_badge[1]}">{_esc(_badge[0])}</span>')
    if opp.get("submitted_by"):
        tags.append(f'<span class="opp-tag owner-tag">Added by {_esc(str(opp["submitted_by"]).split("@")[0])}</span>')

    is_new = False
    created = opp.get("created_at")
    if created:
        try:
            is_new = (datetime.now(timezone.utc) - datetime.fromisoformat(created).replace(tzinfo=timezone.utc)) < timedelta(hours=24)
        except (ValueError, TypeError):
            pass
    title_html = f'<a class="opp-title" href="{_esc(url)}" target="_blank">{title}</a>' if url else f'<span class="opp-title">{title}</span>'
    card_cls = "score-high-card" if score >= 65 else ("score-mid-card" if score >= 40 else "score-low-card")
    summary = s2.get("summary") or ""
    st.markdown(
        f'<div class="opp-card {card_cls}"><div class="opp-card-header"><div style="flex:1;">'
        f'{"<span class=\"new-badge\">NEW</span> " if is_new else ""}{title_html}'
        f'<div class="opp-subtitle"><strong>{state_name}</strong> &middot; {agency}</div>'
        f'<div class="opp-meta">{"".join(tags)}</div></div>'
        f'<div class="score-badge {_score_class(score)}"><div class="score-number">{score if score else "–"}</div><div class="score-label">Fit</div></div>'
        f'</div>{f"<div class=\"opp-summary\">{_esc(summary)}</div>" if summary else ""}'
        f'{extra_meta_html}</div>',
        unsafe_allow_html=True,
    )

    slot = st.container()  # long operations report here, full width, above the details
    if before_details:
        before_details(slot)

    if mode == "pool":
        from oppos.pursuits import claim_opportunity as _claim
        _open_p = OPEN_PURSUITS.get(sid)
        c1, c2, c3, c4 = st.columns([1, 1, 1, 3])
        if _open_p:
            c4.caption(f"Owned by {_open_p.get('owner_name') or _open_p.get('owner_email')} — on their desk.")
        elif not CURRENT_USER.get("can_work"):
            c4.caption(NO_ACCESS_NOTE)
        else:
            with c1:
                if st.button("Grab", key=f"grab_{tab_key}_{sid}", use_container_width=True, type="primary"):
                    _claim(opp, CURRENT_USER)
                    _flash(f"Grabbed — {opp.get('title', '')[:60]} is on My desk", icon="✋")
                    st.rerun()
            with c2:
                with st.popover("Skip", use_container_width=True):
                    reason = st.text_input("Why?", key=f"skip_reason_{tab_key}_{sid}", placeholder="Not a fit — staffing RFP")
                    if st.button("Confirm skip", key=f"skip_go_{tab_key}_{sid}", use_container_width=True):
                        _change_status(opp, "skipped", reason or "Skipped", pipeline_status)
                        _flash(f"Skipped — {opp.get('title', '')[:60]}", icon="⏭️")
                        st.rerun()
            if not score:
                with c3:
                    if st.button("Get a fit score", key=f"score_{tab_key}_{sid}", use_container_width=True):
                        _score_one(opp, slot)
                        st.rerun()
    elif mode == "archive":
        if pipeline_status in ("skipped", "expired", "lost") and sid not in OPEN_PURSUITS and CURRENT_USER.get("can_work"):
            if st.button("Reopen", key=f"reopen_{tab_key}_{sid}"):
                set_pipeline_status(sid, "new", notes="Reopened from Archive")
                _flash(f"Reopened — {opp.get('title', '')[:60]}", icon="↩️")
                st.rerun()

    _s1 = _parse_json(opp.get("stage1_json"))
    _filtered = bool(_s1 and not _s1.get("relevant") and not s2)

    def _details() -> None:
        if score:
            st.caption(f"Fit {score}/100 — how well this matches what Nutrient sells, judged from the listing"
                       + (" and its documents." if opp.get("attachment_text") else ". Scanning its documents (below) makes the score more reliable."))
        if _filtered:
            st.markdown(f'<div class="risk-item">Set aside by the first pass as not relevant — {_esc(_s1.get("reason", ""))}. '
                        f'Use "Get a fit score" if you disagree.</div>', unsafe_allow_html=True)
        elif not s2:
            st.caption("Not scored yet — use \"Get a fit score\" to see how well it matches what we sell.")
        if s2:
            facts = [(l, v) for l, v in (("Pattern", s2.get("pattern_match")), ("Industry", s2.get("industry")),
                                          ("Similar win", s2.get("similar_win")), ("Deployment", s2.get("deployment_recommendation")),
                                          ("Recommendation", s2.get("recommended_action"))) if v and v != "other"]
            if facts:
                st.markdown('<div class="detail-grid">' + "".join(
                    f'<div class="detail-item"><div class="detail-label">{_esc(l)}</div><div class="detail-value">{_esc(str(v))}</div></div>'
                    for l, v in facts) + "</div>", unsafe_allow_html=True)
            col_s, col_r = st.columns(2)
            with col_s:
                for s in s2.get("strengths") or []:
                    st.markdown(f'<div class="strength-item">+ {_esc(point_claim(s))}</div>{_evidence_html(s)}', unsafe_allow_html=True)
            with col_r:
                for r in s2.get("risks") or []:
                    st.markdown(f'<div class="risk-item">- {_esc(point_claim(r))}</div>{_evidence_html(r)}', unsafe_allow_html=True)
            for g in s2.get("knowledge_gaps") or []:
                st.markdown(f'<div class="gap-item">? {_esc(str(g))}</div>', unsafe_allow_html=True)
            if s2.get("competitive_notes"):
                st.caption(f"Competitive: {s2['competitive_notes']}")

        dc1, dc2 = st.columns(2)
        with dc1:
            contact = [opp.get("contact_name"), opp.get("contact_email"), opp.get("contact_phone")]
            lines = [f'<div class="contact-row">{_esc(str(c))}</div>' for c in contact if c] or ['<div class="contact-row" style="color:var(--text-tertiary);">No contact listed</div>']
            extra = [(l, v) for l, v in (("Location", opp.get("place_of_performance")), ("Office", opp.get("office")),
                                          ("NAICS", opp.get("naics_code")), ("Set-aside", opp.get("set_aside")),
                                          ("Notice", opp.get("notice_type"))) if v]
            st.markdown('<div class="detail-label" style="margin-bottom:6px;">Contact</div>' + "".join(lines)
                        + "".join(f'<div class="detail-value" style="margin-top:6px;"><span class="detail-label">{_esc(l)}</span> {_esc(str(v))}</div>' for l, v in extra),
                        unsafe_allow_html=True)
        with dc2:
            posted = opp.get("posted_date")
            st.markdown(f'<div class="detail-label" style="margin-bottom:6px;">Dates</div>'
                        f'<div class="detail-value">Posted {posted[:10] if posted else "unknown"} · {_esc(dl_txt)}</div>'
                        f'<div class="detail-value" style="margin-top:6px;"><span class="detail-label">Source</span> {_esc(SOURCE_LABELS.get(opp.get("source", ""), opp.get("source", "")))}</div>'
                        f'<div class="detail-value" style="margin-top:6px;"><span class="detail-label">Share</span> '
                        f'<a href="{_esc(_app_link("desk" if mode == "desk" else "", sid))}">link to this {"pursuit" if mode == "desk" else "listing"} in OppOS</a></div>',
                        unsafe_allow_html=True)
        desc = opp.get("description") or ""
        if desc:
            st.markdown(f'<div class="detail-label" style="margin-top:12px;margin-bottom:6px;">Description</div>'
                        f'<div class="detail-value" style="line-height:1.6;">{_esc(desc[:2000])}</div>', unsafe_allow_html=True)

        if mode != "archive":
            st.markdown('<div class="detail-label" style="margin-top:14px;margin-bottom:6px;">Documents</div>', unsafe_allow_html=True)
            _render_deep_scan(opp, tab_key, slot)
        att_dir = _att_dir(sid)
        files = sorted(f for f in att_dir.iterdir() if f.is_file()) if att_dir.is_dir() else []
        if files:
            fc = st.columns(min(len(files), 4))
            for i, f in enumerate(files):
                with fc[i % len(fc)], open(f, "rb") as fh:
                    st.download_button(f.name[:28], data=fh.read(), file_name=f.name, key=f"dl_{tab_key}_{sid}_{f.name}", use_container_width=True)

    if details:
        with st.expander("Details"):
            _details()
    return _details


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
        att = opp.get("attachment_text") or ""
        st.write(f"📄 Using the RFP description" + (f" and {len(att):,} characters of attachment text" if att else " — no attachments loaded (load them first for a better draft)"))
        st.write("🔒 Security items get the Trust Center standard answer (NDA access on request); explicit asks for a specific statement or artifact are "
                 + ("answered from the approved compliance file" if comp["approved"] else "marked [SECURITY TO CONFIRM]"))

        # Dogfood: Nutrient Data Extraction API maps the RFP PDFs to a requirements schema with page citations.
        extracted = None
        att_dir = _att_dir(sid)
        pdfs = sorted(f for f in att_dir.iterdir() if f.is_file() and f.suffix.lower() == ".pdf") if att_dir.is_dir() else []
        if pdfs:
            from oppos.drafting.extraction import extract_rfp_requirements, extraction_available
            if extraction_available():
                extracted = extract_rfp_requirements(pdfs, on_progress=lambda m: st.write(f"🧩 {m}"))
                st_ = extracted.get("stats") or {}
                if extracted["requirements"]:
                    st.write(f"✓ Nutrient Data Extraction: {st_['requirements']} requirements ({st_['mandatory']} mandatory) from "
                             f"{extracted['pages']} pages · {extracted['credits_cost']} credits"
                             + (f" · {extracted['credits_remaining']} remaining" if extracted.get("credits_remaining") is not None else ""))
                for sk in extracted.get("skipped", []):
                    st.write(f"⚠️ Skipped {sk}")
                for er in extracted.get("errors", []):
                    st.write(f"⚠️ Extraction error — {er}")
                if not extracted["requirements"]:
                    # A forms-only or instructions-only package yields no requirement items but still carries the
                    # authoritative deadline / method / forms / criteria — keep them; discard only an empty result.
                    kept = any(extracted.get(k) for k in ("solicitation", "required_forms", "evaluation_criteria"))
                    st.write("ℹ️ No requirement items extracted" + (" — keeping the extracted submission facts" if kept else ""))
                    if not kept:
                        extracted = None
            else:
                st.write("ℹ️ NUTRIENT_API_KEY not set — drafting from text only")
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


def _submission_html(opp: dict, pursuit: dict, draft: dict | None) -> str:
    """'How to submit' for one pursuit: where (portal + registration, email, or mail), when (due, questions),
    who (contact), what (format, forms). Pursuit details win; the RFP documents (draft extraction) fill the gaps;
    whatever is still unknown is named so the person knows what to find out."""
    from oppos.pursuits import REGISTRATION_LABELS
    sub = (draft or {}).get("submission") or {}
    method = (pursuit.get("submission_method") or "unknown").lower()
    from_docs = False
    if method == "unknown" and str(sub.get("method") or "").lower() in ("portal", "email", "mail", "in_person"):
        method, from_docs = str(sub["method"]).lower(), True
    reg = PORTAL_REGS.get(str(pursuit.get("portal") or opp.get("source") or "")) or {}
    portal_name = reg.get("display_name") or SOURCE_LABELS.get(opp.get("source", ""), "") or ""
    portal_url = reg.get("url") or opp.get("url") or ""
    contact = [opp.get("contact_name"), opp.get("contact_email"), opp.get("contact_phone")]
    missing = []

    # where
    if method == "portal":
        where = f"On the portal{': ' + _esc(portal_name) if portal_name else ''}"
        if portal_url:
            where += f' · <a href="{_esc(portal_url)}" target="_blank">open ↗</a>'
        reg_status = pursuit.get("registration_status") or reg.get("status") or "unknown"
        _request = (f' · <a href="{_esc(PORTAL_ACCESS_REQUEST_URL)}" target="_blank">request an account ↗</a>'
                    if PORTAL_ACCESS_REQUEST_URL else "")
        if reg_status in ("registered", "not_required"):
            where += f' · <span class="sub-ok">{_esc(REGISTRATION_LABELS.get(reg_status, reg_status))}</span>'
        elif reg_status == "unknown":
            where += ' · <span class="sub-warn">registration status unknown</span> — check whether we have an account' + _request
        elif reg_status == "in_progress":
            where += ' · <span class="sub-warn">account requested, pending</span>'
        else:
            lead = reg.get("lead_time_days")
            where += (f' · <span class="sub-bad">No account yet{f", allow ~{int(lead)} days" if lead else ""}</span>'
                      + (_request or " — ask an admin to add the service desk link (PORTAL_ACCESS_REQUEST_URL)"))
        if reg.get("login_owner"):
            where += f" · login held by {_esc(str(reg['login_owner']))}"
    elif method == "email":
        to = str(sub.get("email_to") or opp.get("contact_email") or "")
        where = "By email" + (f' to <a href="mailto:{_esc(to)}">{_esc(to)}</a>' if to else "")
        if sub.get("email_subject"):
            where += f' · subject line must be <code>{_esc(str(sub["email_subject"]))}</code>'
        if sub.get("delivery"):
            where += f" · {_esc(str(sub['delivery'])[:160])}"
        if not to:
            missing.append("the address to send it to")
    elif method == "mail":
        where = "By mail / hand delivery" + (f" · {_esc(opp.get('office') or opp.get('place_of_performance') or '')}" if (opp.get("office") or opp.get("place_of_performance")) else "")
    elif method == "in_person":
        where = "In person" + (f" · {_esc(opp.get('office') or '')}" if opp.get("office") else "")
    else:
        where = '<span class="sub-warn">Submission method not known yet</span>'
        if opp.get("url"):
            where += f' · listing: <a href="{_esc(opp["url"])}" target="_blank">open ↗</a>'
        missing.append("how it is submitted")
    if from_docs:
        where += ' <span class="sub-src">(from the RFP documents)</span>'

    # when
    due = pursuit.get("submission_deadline") or (opp.get("response_deadline") or "")[:10]
    when_bits = []
    if due:
        when_bits.append(f"Due {_esc(str(due)[:10])}" + (f" (the RFP says {_esc(str(sub['deadline']))})" if sub.get("deadline") and sub["deadline"] != "unknown" and str(sub["deadline"])[:10] != str(due)[:10] else ""))
    else:
        missing.append("the due date")
    qa = pursuit.get("qa_deadline") or sub.get("questions_deadline") or ""
    if qa:
        when_bits.append(f"questions by {_esc(str(qa)[:40])}")

    # who
    who = " · ".join(_esc(str(c)) for c in contact if c)
    if not who:
        missing.append("a contact")

    # what
    forms = [str(x) for x in ((draft or {}).get("required_forms") or [])][:5]
    fmt = [str(x) for x in (sub.get("format_requirements") or []) if not str(x).lower().startswith("required form")][:4]  # forms have their own line

    rows = [f'<div><span class="sub-k">Where</span>{where}</div>']
    if when_bits:
        rows.append(f'<div><span class="sub-k">When</span>{" · ".join(when_bits)}</div>')
    if who:
        rows.append(f'<div><span class="sub-k">Who</span>{who}</div>')
    if fmt:
        rows.append(f'<div><span class="sub-k">Format</span>{_esc("; ".join(fmt))}</div>')
    if forms:
        rows.append(f'<div><span class="sub-k">Forms</span>{_esc("; ".join(forms))}</div>')
    if missing:
        rows.append(f'<div class="sub-missing">Still to find out: {_esc(", ".join(missing))} — fill it in under Pursuit details'
                    + ("" if draft else ", or draft the response and the RFP documents are read for it") + ".</div>")
    return '<div class="sub-box"><div class="sub-title">How to submit</div>' + "".join(rows) + "</div>"


def _render_pursuit_panel(opp: dict, pursuit: dict, events: list[dict]) -> None:
    """Workspace for one pursuit: status strip, one action row for its stage, then the checklist, details,
    response and activity folded away. `events` is this pursuit's slice of the desk's single events query."""
    import json as _json
    from oppos.outputs.slack_alerts import build_sdr_message
    from oppos.outputs.slack_pursuits import channel_url
    from oppos.pursuits import (
        CHECKLIST, REGISTRATION_LABELS, REGISTRATION_STATUSES, SUBMISSION_METHODS,
        checklist_progress, checklist_state, days_until, deadline_date, release_claim as _release_claim,
        save_pursuit_fields, stage_label as _stage_lbl, transition_pursuit,
    )

    sid = opp.get("source_id", "")
    k = f"pp_{sid}"
    title = opp.get("title") or "Untitled"
    _stage = pursuit.get("status") or "active"
    can_edit = bool(CURRENT_USER.get("is_admin")) or (pursuit.get("owner_email") or "").lower() == CURRENT_USER["email"]
    owner = pursuit.get("owner_name") or pursuit.get("owner_email") or "Unassigned"
    npid = pursuit.get("notion_page_id") or opp.get("notion_page_id")
    _draft = _parse_json(pursuit.get("draft_json")) or None

    # ── Where it stands (rendered inside the card) ───────────────
    due_raw = pursuit.get("submission_deadline") or opp.get("response_deadline")
    dleft = days_until(due_raw)
    done, total = checklist_progress(pursuit)
    if dleft is None:
        due_txt, due_cls = "No deadline set", "pp-warn"
    elif dleft < 0:
        due_txt, due_cls = f"Overdue by {-dleft}d", "pp-bad"
    else:
        due_txt, due_cls = ("Due today" if dleft == 0 else f"Due in {dleft}d · {str(due_raw)[:10]}"), ("pp-bad" if dleft <= 3 else "pp-warn" if dleft <= 7 else "pp-ok")
    reg_status = pursuit.get("registration_status") or "unknown"
    reg_cls = {"registered": "pp-ok", "not_required": "pp-ok", "in_progress": "pp-warn", "not_registered": "pp-bad"}.get(reg_status, "")
    links = [f'<a href="{_esc(_app_link("desk", sid))}" title="Link to this pursuit — copy from the address bar or right-click to copy">Link to this</a>']
    if npid:
        links.append(f'<a href="https://notion.so/{str(npid).replace("-", "")}" target="_blank">Notion ↗</a>')
    if pursuit.get("slack_channel_id"):
        links.append(f'<a href="{channel_url(pursuit["slack_channel_id"])}" target="_blank">#{_esc(pursuit.get("slack_channel_name") or "slack")} ↗</a>')
    strip = (
        f'<div class="pp-strip pp-in-card"><span class="pp-owner">{_esc(owner)}</span>'
        f'<span class="pp-pill {"pp-ok" if _stage == "active" else ""}">{_esc(_stage_lbl(_stage))}</span>'
        f'<span class="pp-pill {due_cls}">{due_txt}</span>'
        + (f'<span class="pp-pill {reg_cls}">{_esc(REGISTRATION_LABELS.get(reg_status, reg_status))}</span>' if reg_status != "unknown" else "")
        + f'<span class="pp-pill">{done}/{total} checklist done</span>'
        + f'<span class="pp-links">{"".join(links)}</span></div>'
        + (f'<div class="pp-next">Next: {_esc(pursuit["next_action"][:120])}</div>' if pursuit.get("next_action") else "")
        + _submission_html(opp, pursuit, _draft)
    )

    def _actions(slot) -> None:
        # One row, the stage's main action first. Progress of long actions reports into `slot`, full width.
        if not can_edit:
            st.caption(f"Owned by {owner}. Actions are available to the owner and admins.")
            return
        if _stage == "evaluating":
            a1, a2, a3 = st.columns([1, 1, 4])
            with a1:
                if st.button("Start pursuing", key=f"{k}_start", use_container_width=True, type="primary"):
                    with slot:
                        _pursue_opportunity(opp, reason=pursuit.get("reason") or "")
                    st.rerun()
            with a2:
                if st.button("Put it back", key=f"{k}_release", use_container_width=True):
                    _release_claim(opp, CURRENT_USER)
                    _flash(f"Put back — {title[:60]} is in Find RFPs again", icon="↩️")
                    st.rerun()
            a3.caption("Worth going after? Start pursuing: it opens a Notion page and a Slack channel for it and sets reminders. "
                       "Not for us? Put it back for someone else.")
            return
        a1, a2, a3, a4 = st.columns([1, 1, 1, 3])
        if _stage == "active":
            with a1:
                if st.button("Regenerate draft" if _draft else "Draft response", key=f"{k}_draft", use_container_width=True, type="secondary" if _draft else "primary"):
                    with slot:
                        _run_draft(opp, pursuit)
                    st.rerun()
            with a2:
                with st.popover("Mark submitted", use_container_width=True):
                    sub_note = st.text_input("Submission note", key=f"{k}_sub_note", placeholder="Submitted via portal, confirmation #…")
                    if st.button("Confirm submitted", key=f"{k}_sub_go", use_container_width=True, type="primary"):
                        transition_pursuit(opp, "submitted", CURRENT_USER, sub_note)
                        _flash(f"Submitted — {title[:60]}", icon="📨")
                        st.rerun()
        else:  # submitted — awaiting the agency
            with a1:
                with st.popover("Record outcome", use_container_width=True):
                    outcome = st.radio("Outcome", ["won", "lost"], horizontal=True, key=f"{k}_outcome", format_func=str.title)
                    out_note = st.text_input("Notes", key=f"{k}_out_note", placeholder="Award details, competitor, debrief…")
                    if st.button("Save outcome", key=f"{k}_out_go", use_container_width=True, type="primary"):
                        transition_pursuit(opp, outcome, CURRENT_USER, out_note)
                        _flash(f"{outcome.title()} — {title[:60]}", icon="🏁")
                        st.rerun()
        with a3:
            with st.popover("More", use_container_width=True):
                if _draft and npid and _stage == "active":
                    _render_notion_append(opp, pursuit, _draft, npid, k, slot)
                if st.button("Re-push to Notion" if npid else "Push to Notion", key=f"{k}_push", use_container_width=True):
                    with slot:
                        _push_to_notion(opp)
                st.markdown('<div class="detail-label" style="margin-top:10px;">Salesforce opportunity — paste to the SDR channel</div>', unsafe_allow_html=True)
                st.code(build_sdr_message(opp), language=None)
                if _stage == "active":
                    st.markdown('<div class="detail-label" style="margin-top:10px;">Abandon</div>', unsafe_allow_html=True)
                    ab_reason = st.text_input("Why?", key=f"{k}_ab_reason", placeholder="Timeline too tight, requirements changed…")
                    if st.button("Abandon this pursuit", key=f"{k}_ab_go", use_container_width=True):
                        transition_pursuit(opp, "abandoned", CURRENT_USER, ab_reason)
                        _flash(f"Abandoned — {title[:60]}", icon="🗑️")
                        st.rerun()
        with a4:
            if _draft:
                _st = _draft.get("stats") or {}
                _when = str(_draft.get("generated_at", ""))[:10]
                try:
                    _when = datetime.fromisoformat(_when).strftime("%b %-d")
                except ValueError:
                    pass
                st.caption(f"Draft from {_when} · {_st.get('requirements', 0)} requirements · {_st.get('needs_human', 0)} need your input"
                           + (" · appended to Notion" if (_draft.get("notion_append") or {}).get("complete") else "") + ". Open it under Response below.")
            elif _stage == "active":
                st.caption("Next: Draft response writes a first answer to every requirement in the RFP."
                           + (" For the best draft, load the RFP's documents first (Details → Documents)." if not opp.get("attachment_text") else ""))

    _details = render_card(opp, "desk", "desk", extra_meta_html=strip, before_details=_actions, details=False)

    # Portal registration status is team knowledge: let whoever knows it set it from here (see Admin for the full table).
    _portal_key = str(pursuit.get("portal") or opp.get("source") or "")
    _preg = PORTAL_REGS.get(_portal_key) or {}
    if _portal_key and _portal_key != "manual" and (_preg.get("status") or "unknown") in ("unknown", "not_registered", "in_progress") \
            and CURRENT_USER.get("can_work"):
        from oppos.storage.db import upsert_portal_registration
        g1, g2, g3 = st.columns([1.3, 1.3, 3.4], vertical_alignment="center")
        _pname = _preg.get("display_name") or SOURCE_LABELS.get(_portal_key, _portal_key)
        with g1:
            if st.button("We're registered here", key=f"{k}_reg_yes", use_container_width=True):
                upsert_portal_registration(_portal_key, status="registered")
                save_pursuit_fields(sid, CURRENT_USER, registration_status="registered")
                _flash(f"Recorded: Nutrient is registered on {_pname}", icon="✅")
                st.rerun()
        with g2:
            if (_preg.get("status") or "unknown") != "in_progress" and st.button("Account requested", key=f"{k}_reg_req", use_container_width=True):
                upsert_portal_registration(_portal_key, status="in_progress")
                save_pursuit_fields(sid, CURRENT_USER, registration_status="in_progress")
                _flash(f"Recorded: account requested on {_pname}", icon="⏳")
                st.rerun()
        g3.caption(f"Portal: {_pname}. Either answer applies to every RFP from it. Vendor ID, who holds the login and lead time: Admin → Portal registrations.")

    # ── Everything else, one tab strip ──────────────────────────
    t_check, t_resp, t_det, t_pd, t_act = st.tabs([f"Checklist · {done}/{total}", "Response" + (" ✓" if _draft else ""),
                                                   "About this RFP", "Pursuit details", f"Activity · {len(events)}"])
    with t_check:
        state = checklist_state(pursuit)
        cols = st.columns(3)
        new_state = {}
        for i, (key, label) in enumerate(CHECKLIST):
            with cols[i % 3]:
                new_state[key] = st.checkbox(label, value=state[key], key=f"{k}_ck_{key}", disabled=not can_edit)
        if can_edit and new_state != state:
            save_pursuit_fields(sid, CURRENT_USER, checklist_json=_json.dumps(new_state))
            st.rerun()

    with t_det:
        _details()

    with t_pd:
        if can_edit:
            c1, c2, c3 = st.columns(3)
            with c1:
                owner_email = st.text_input("Owner email", value=pursuit.get("owner_email") or "", key=f"{k}_owner")
                owner_name = st.text_input("Owner name", value=pursuit.get("owner_name") or "", key=f"{k}_owner_name")
            with c2:
                sub_dl = st.date_input("Submission deadline", value=deadline_date(due_raw), key=f"{k}_sub", format="YYYY-MM-DD")
                qa_dl = st.date_input("Questions deadline", value=deadline_date(pursuit.get("qa_deadline")), key=f"{k}_qa", format="YYYY-MM-DD")
            with c3:
                _m = pursuit.get("submission_method") or "unknown"
                method = st.selectbox("Submission method", SUBMISSION_METHODS,
                                      index=SUBMISSION_METHODS.index(_m) if _m in SUBMISSION_METHODS else 0, key=f"{k}_method")
                reg = st.selectbox("Vendor registration", REGISTRATION_STATUSES,
                                   index=REGISTRATION_STATUSES.index(reg_status) if reg_status in REGISTRATION_STATUSES else 0,
                                   format_func=lambda v: REGISTRATION_LABELS.get(v, v), key=f"{k}_reg")
            next_action = st.text_input("Next action", value=pursuit.get("next_action") or "", key=f"{k}_next",
                                        placeholder="e.g. Submit questions by Friday; confirm vendor registration with ops")
            if st.button("Save details", key=f"{k}_save"):
                save_pursuit_fields(
                    sid, CURRENT_USER,
                    owner_email=owner_email.strip().lower() or None, owner_name=owner_name.strip() or None,
                    submission_deadline=sub_dl.isoformat() if sub_dl else None,
                    qa_deadline=qa_dl.isoformat() if qa_dl else None,
                    submission_method=method, registration_status=reg, next_action=next_action.strip() or None,
                )
                _flash("Pursuit details saved")
                st.rerun()
        else:
            d1, d2, d3 = st.columns(3)
            d1.markdown(f"**Owner**  \n{_esc(owner)}")
            d2.markdown(f"**Submission deadline**  \n{_esc(str(due_raw or '—'))[:10]}  \n**Questions deadline**  \n{_esc(str(pursuit.get('qa_deadline') or '—'))}")
            d3.markdown(f"**Method**  \n{_esc(pursuit.get('submission_method') or 'unknown')}  \n**Registration**  \n{_esc(REGISTRATION_LABELS.get(reg_status, reg_status))}")
            if pursuit.get("next_action"):
                st.markdown(f"**Next action**  \n{_esc(pursuit['next_action'])}")

    with t_resp:
        if _draft:
            _render_response(opp, pursuit, _draft, k)
        else:
            st.caption("No response yet. Draft response (above) writes a first answer to every requirement; the document and the "
                       "Word / PDF downloads appear here.")

    with t_act:
        if not events:
            st.caption("No activity yet.")
        for ev in events:
            ts = str(ev.get("ts") or "")[:16].replace("T", " ")
            st.markdown(f'<div class="pp-event">{_esc(ts)} · <b>{_esc(str(ev.get("kind") or ""))}</b> · '
                        f'{_esc(str(ev.get("actor") or ""))} — {_esc(str(ev.get("detail") or ""))}</div>', unsafe_allow_html=True)


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


def _render_response(opp: dict, pursuit: dict, _draft: dict, k: str) -> None:
    """The drafted answers and the exportable document, in one fold."""
    _reqs = _draft.get("requirements") or []
    if True:  # (was a fold; the Response tab is the container now)
        # The document is the deliverable: open it, edit in place, download as Word or PDF. (It is built from the
        # draft by the Nutrient Document Authoring SDK in the browser; nothing is uploaded anywhere.)
        from oppos.dashboard.docauth import response_editor
        from oppos.drafting.document import file_stem, render_markdown
        _reg = PORTAL_REGS.get(str(pursuit.get("portal") or "")) or {}
        _stem = file_stem(opp)
        _open_key = f"{k}_doc_open"
        rc1, rc2 = st.columns([1, 4])
        with rc1:
            if not st.session_state.get(_open_key):
                if st.button("Open response document", key=f"{k}_doc_open_btn", use_container_width=True, type="primary"):
                    st.session_state[_open_key] = True
                    st.rerun()
            elif st.button("Close document", key=f"{k}_doc_close_btn", use_container_width=True):
                st.session_state[_open_key] = False
                st.rerun()
        rc2.caption("Executive summary, the answers under the RFP's own headings, delivery approach, requirements matrix and the "
                    "security evidence appendix. Review the highlighted markers, edit in place, preview the PDF, then download it as a Word document or PDF."
                    + (" Downloads carry an evaluation watermark until the licence key is set." if not DOCAUTH_LICENSE_KEY else ""))
        if st.session_state.get(_open_key):
            _md = render_markdown(_draft, opp, author=CURRENT_USER.get("name", ""),
                                  pursuit=dict(pursuit, portal_name=_reg.get("display_name") or ""))
            response_editor(_md, _stem, DOCAUTH_LICENSE_KEY, viewer_license_key=VIEWER_LICENSE_KEY)

        if _draft.get("executive_summary"):
            st.markdown('<div class="detail-label" style="margin-top:14px;">Executive summary</div>', unsafe_allow_html=True)
            st.write(_draft["executive_summary"])
        if _draft.get("win_themes"):
            st.caption("Win themes: " + " · ".join(_draft["win_themes"]))
        _sub = _draft.get("submission") or {}
        st.caption(f"{_draft.get('rfp_type', '')} · submission {_sub.get('method', 'unknown')} · deadline {_sub.get('deadline', 'unknown')}"
                   + (f" · questions due {_sub['questions_deadline']}" if _sub.get("questions_deadline") else "")
                   + (" · " + "; ".join(_sub.get("format_requirements", [])[:3]) if _sub.get("format_requirements") else ""))
        if _draft.get("evaluation_criteria"):
            st.caption("Evaluation criteria: " + " · ".join(f"{c['criterion']}" + (f" ({c['weight']})" if c.get("weight") else "") for c in _draft["evaluation_criteria"]))
        if _draft.get("required_forms"):
            st.caption("Required forms: " + " · ".join(_draft["required_forms"]))
        _ex = _draft.get("extraction")
        if _ex and _ex.get("stats"):
            st.caption(f"Requirements extracted with Nutrient Data Extraction ({_ex.get('mode')}): {_ex['stats']['requirements']} items, "
                       f"{_ex['stats']['mandatory']} mandatory, from {_ex.get('pages')} pages · {_ex.get('credits_cost')} credits"
                       + (f" · {_draft['stats']['missing_from_model']} not answered by the model (marked [NOT DRAFTED])" if (_draft.get("stats") or {}).get("missing_from_model") else ""))
        for r in _reqs:
            _conf_cls = {"high": "pp-ok", "medium": "pp-warn", "low": "pp-bad"}.get(r.get("confidence"), "")
            st.markdown(
                f'<div class="pp-strip" style="margin-top:14px;"><span class="pp-owner">{_esc(r["id"])}'
                + (f' · {_esc(r["section"])}' if r.get("section") else "")
                + (f' · {_esc(r["file"])} p.{r["page"]}' if r.get("page") and r.get("file") else f' · p.{r["page"]}' if r.get("page") else "") + "</span>"
                f'<span class="pp-pill">{_esc(str(r.get("category", "")).replace("_", " "))}</span>'
                f'<span class="pp-pill {_conf_cls}">{_esc(str(r.get("confidence", "")))} confidence</span></div>'
                f'<div class="evidence-quote" style="margin-left:0;">{_esc(r.get("text", ""))}</div>',
                unsafe_allow_html=True,
            )
            st.write(r.get("response", ""))
            if r.get("human_todo"):
                st.markdown(f'<div class="gap-item">? {_esc(r["human_todo"])}</div>', unsafe_allow_html=True)
            if r.get("sources"):
                st.caption("Sources: " + "; ".join(r["sources"][:4]))
        for _title, _key in (("Open questions for Q&A", "open_questions"), ("Assumptions", "assumptions"), ("Do not claim", "do_not_claim")):
            _items = _draft.get(_key) or []
            if _items:
                st.markdown(f'<div class="detail-label" style="margin-top:14px;">{_title}</div>', unsafe_allow_html=True)
                for x in _items:
                    st.markdown(f'<div class="gap-item">• {_esc(x)}</div>', unsafe_allow_html=True)


def _unclaimed(rows: list[dict]) -> tuple[list[dict], int]:
    """Split Find-RFPs rows into (shown, number hidden because they belong to a desk).

    Anything with a pursuit record — claimed, pursuing, submitted or closed — is managed from
    its owner's desk and never rendered (or counted) in the shared pool. The pool is also
    strict about exclusions, so an excluded-source row can't be re-claimed from here.
    """
    pool = [r for r in rows if r.get("source") not in EXCLUDED_SOURCES]
    kept = [r for r in pool if r.get("source_id") not in PURSUED_IDS]
    return kept, len(pool) - len(kept)


def _claimed_note(n: int) -> str:
    return f' &middot; <span style="color: var(--text-tertiary);">{n} on desks — see My desk → Team</span>' if n else ""


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
    """Find RFPs — the shared pool of unclaimed listings. Open ones to grab, or the archive."""
    h1, h2, h3 = st.columns([1, 1, 3])
    with h1:
        scan_clicked = st.button("Scan for new RFPs", use_container_width=True, type="primary")
    with h2:
        if st.button("Add an RFP", use_container_width=True, disabled=not CURRENT_USER.get("can_work")):
            _manual_rfp_dialog()
    h3.caption((f"Everything the scanner found that nobody has taken yet. Grab anything worth a look — it moves to your desk. "
                f"Sourced one yourself? Add an RFP takes a link, a file, or just what you know. "
                if CURRENT_USER.get("can_work") else f"Everything the scanner found that nobody has taken yet. {NO_ACCESS_NOTE} ")
               + f"Last scan {_ago(_cached_meta('last_scan'))}.")

    if scan_clicked:
        stats = _run_scan()
        _flash(f"Scan done — {stats['new']} new, {stats['scored']} scored, {stats['fetched']} listings checked"
               + (f" · {len(stats['errors'])} source error(s)" if stats["errors"] else ""), icon="🔎")
        st.session_state["last_scan_errors"] = stats["errors"]
        st.rerun()
    _errs = st.session_state.pop("last_scan_errors", None)
    if _errs:
        with st.expander(f"{len(_errs)} source(s) had errors on the last scan"):
            for err in _errs:
                st.text(err)

    def _set_aside(r: dict) -> bool:
        """Rejected by the first pass and never looked at by a person: stored (so it is not re-scanned) but not a
        listing to show. Notes written by the app itself (the deadline sweep, auto-expiry) do not count as a person."""
        notes = str(r.get("pipeline_notes") or "")
        if _score_of(r) or (notes and not notes.startswith(("Deadline within", "Auto-"))):
            return False
        s1 = _parse_json(r.get("stage1_json"))
        return bool(s1) and not s1.get("relevant")
    open_rows, _claimed_n = _unclaimed([r for r in get_all_scored(0)
                                        if (r.get("pipeline_status") or "new") in ("new", "qualified", "expiring_soon") and not _set_aside(r)])
    archive_rows, _ = _unclaimed([r for r in get_all_scored(0) if (r.get("pipeline_status") or "new") in ("won", "lost", "skipped", "expired")])

    tab_open, tab_archive = st.tabs([f"Open ({len(open_rows)})", f"Archive ({len(archive_rows)})"])

    with tab_open:
        f1, f2, f3, f4 = st.columns([2, 1, 2, 1])
        with f1:
            min_score = st.slider("Minimum fit", 0, 100, 40, step=5, key="pool_score")
        with f2:
            sort_by = st.selectbox("Sort", ["Fit", "Deadline", "Newest"], key="pool_sort")
        with f3:
            source_filter = st.multiselect("Source", sorted(SOURCE_LABELS, key=SOURCE_LABELS.get),
                                           format_func=lambda s: SOURCE_LABELS.get(s, s), key="pool_source", placeholder="All sources")
        unscored = [r for r in open_rows if not _score_of(r)]
        with f4:
            st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            if unscored and st.button(f"Score all {len(unscored)} unscored", key="pool_score_all", use_container_width=True):
                _score_batch(unscored)
                st.rerun()

        rows = [r for r in open_rows if _score_of(r) >= min_score or not _score_of(r)]
        _open_q = st.query_params.get("open")
        if _open_q:  # shared link to one listing: show it first regardless of the filters
            _hit = next((r for r in open_rows if r.get("source_id") == _open_q), None)
            if _hit:
                rows = [_hit] + [r for r in rows if r.get("source_id") != _open_q]
            else:
                _flash("That listing is not open any more — it may be on someone's desk or archived.", icon="ℹ️")
        if source_filter:
            rows = [r for r in rows if r.get("source") in source_filter]
        if sort_by == "Deadline":
            rows.sort(key=lambda r: r.get("response_deadline") or "9999")
        elif sort_by == "Newest":
            rows.sort(key=lambda r: r.get("created_at") or r.get("posted_date") or "", reverse=True)
        else:
            rows.sort(key=lambda r: (-_score_of(r), r.get("response_deadline") or "9999"))

        st.caption(f"{len(rows)} open listing{'s' if len(rows) != 1 else ''}"
                   + (f" · {len(unscored)} not scored yet (shown regardless of the minimum)" if unscored else "")
                   + (f" · {_claimed_n} on desks" if _claimed_n else ""))
        if not rows:
            render_empty("Nothing open matches. Lower the minimum fit or scan for new RFPs.")
        _show_more(rows, "pool_show", lambda o: render_card(o, "pool", "pool"))

    with tab_archive:
        archive_rows.sort(key=lambda r: r.get("pipeline_updated_at") or r.get("updated_at") or "", reverse=True)
        by = {s: sum(1 for r in archive_rows if r.get("pipeline_status") == s) for s in ("won", "lost", "skipped", "expired")}
        st.caption(" · ".join(f"{n} {s}" for s, n in by.items() if n) or "Nothing archived yet.")
        _show_more(archive_rows, "arch_show", lambda o: render_card(o, "arch", "archive"))


def page_desk() -> None:
    """My desk — what the signed-in user has claimed or is working, by stage; Team shows everyone's."""
    import html as _html
    from oppos.pursuits import OPEN_STAGES, days_until as _du, stage_label
    from oppos.storage.db import add_pursuit_event, create_pursuit, get_opps_by_ids, get_pursuit_events_for

    me = CURRENT_USER["email"]
    all_p = _cached_pursuits()
    # Deep link (Slack buttons): /desk?open=<source_id> selects that pursuit, switching to Team if it is not mine.
    _open_q = st.query_params.get("open")
    if _open_q and st.session_state.get("desk_deeplink") != _open_q:
        st.session_state["desk_deeplink"] = _open_q
        _target = next((p for p in all_p if p["source_id"] == _open_q), None)
        if _target:
            _mine = (_target.get("owner_email") or "").lower() == me
            st.session_state["pursuit_view"] = "Mine" if _mine else "Team"
            st.session_state[f"desk_selected_{'Mine' if _mine else 'Team'}"] = _open_q
        else:
            _flash("That RFP is no longer on anyone's desk.", icon="ℹ️")
    v1, v2 = st.columns([1, 4])
    with v1:
        _view = st.radio("View", ["Mine", "Team"], horizontal=True, label_visibility="collapsed", key="pursuit_view")
    rows_p = all_p if _view == "Team" else [p for p in all_p if (p.get("owner_email") or "").lower() == me]
    open_p = [p for p in rows_p if p.get("status") in OPEN_STAGES]
    by_stage = {
        "evaluating": [p for p in rows_p if p.get("status") == "evaluating"],
        "active": [p for p in rows_p if p.get("status") == "active"],
        "submitted": [p for p in rows_p if p.get("status") == "submitted"],
        "closed": [p for p in rows_p if p.get("status") in ("won", "lost", "abandoned", "released")],
    }
    live_ids = [p["source_id"] for p in rows_p if p.get("status") in ("evaluating", "active", "submitted")]
    # Two queries for the whole desk, however many pursuits: the rows and their activity.
    opps = get_opps_by_ids(live_ids + [p["source_id"] for p in by_stage["closed"][:50]])
    events = get_pursuit_events_for(live_ids, limit_per=40)

    _next = sorted((d for d in (_du(p.get("submission_deadline")) for p in open_p) if d is not None))
    _cnt = lambda *sts: sum(1 for p in rows_p if p.get("status") in sts)
    with v2:
        st.caption(f"{_cnt('evaluating')} grabbed · {_cnt('active')} pursuing · {_cnt('submitted')} submitted · "
                   f"{_cnt('won')} won · {_cnt('lost', 'abandoned')} lost"
                   + (f" · next due in {_next[0]}d" if _next and _next[0] >= 0 else " · an item is overdue" if _next else ""))

    # Legacy in-progress / submitted RFPs with no pursuit record — Team view can adopt them.
    _have = {p["source_id"] for p in all_p}
    _orphans = {"active": [o for o in _rows_by_status("in_progress") if o["source_id"] not in _have],
                "submitted": [o for o in _rows_by_status("submitted") if o["source_id"] not in _have]}
    _n_orphans = sum(len(v) for v in _orphans.values())
    if _n_orphans and _view == "Team":
        o1, o2 = st.columns([3, 1])
        o1.caption(f"{_n_orphans} RFP(s) were marked in progress or submitted before pursuit tracking existed and have no owner.")
        if o2.button("Adopt them as mine", key="adopt_orphans", use_container_width=True):
            for stage, items in _orphans.items():
                for o in items:
                    create_pursuit(o["source_id"], owner_email=me, owner_name=CURRENT_USER["name"], lob=o.get("lob"),
                                   reason=o.get("pipeline_notes") or f"Adopted from legacy {stage}", status=stage,
                                   submission_deadline=(o.get("response_deadline") or "")[:10] or None,
                                   portal=o.get("source"), notion_page_id=o.get("notion_page_id"), created_by=me)
                    add_pursuit_event(o["source_id"], me, "adopted", f"Adopted from legacy {o.get('pipeline_status')}")
            _flash(f"Adopted {_n_orphans} item(s)")
            st.rerun()

    if not any(by_stage.values()):
        render_empty("Nothing on your desk yet.")
        st.caption(NO_ACCESS_NOTE if not CURRENT_USER.get("can_work") else
                   "How it works: Find RFPs lists what the scanner found. Grab one and it lands here. Start pursuing, draft the response, "
                   "download it as a Word document, submit it, then record the outcome.")
        return

    # One line per pursuit, grouped by stage; the selected one opens as the workspace below.
    sections = (("evaluating", "Grabbed — decide", "Go after it, or put it back."),
                ("active", "Pursuing", "Draft, download, submit, mark submitted."),
                ("submitted", "Submitted — waiting on the agency", "Record Won or Lost when you hear back."))
    ordered = [(stage, p_) for stage, _, _ in sections for p_ in by_stage[stage]]
    ids = [p_["source_id"] for _, p_ in ordered]
    sel_key = f"desk_selected_{_view}"
    selected = st.session_state.get(sel_key)
    if selected not in ids:
        selected = ids[0] if ids else None
    for stage, title, hint in sections:
        items = by_stage[stage]
        if not items:
            continue
        st.markdown(f'<div class="desk-section">{title} · {len(items)} <span>{hint}</span></div>', unsafe_allow_html=True)
        for p_ in items:
            o = opps.get(p_["source_id"]) or {}
            sid = p_["source_id"]
            due = p_.get("submission_deadline") or (o.get("response_deadline") or "")[:10]
            dl = _du(due)
            due_txt = ("" if dl is None else f"overdue by {-dl}d" if dl < 0 else "due today" if dl == 0 else f"due in {dl}d")
            due_cls = "" if dl is None else ("desk-bad" if dl <= 3 else "desk-warn" if dl <= 7 else "")
            bits = [b for b in (SOURCE_STATE_MAP.get(o.get("source", ""), ""), (o.get("agency") or "")[:60]) if b]
            next_txt = p_.get("next_action") or ""
            c1, c2, c3 = st.columns([6, 1.8, 0.9], vertical_alignment="center")
            c1.markdown(
                f'<div class="desk-row{" sel" if sid == selected else ""}"><div class="desk-title">{_esc(o.get("title") or sid)}</div>'
                f'<div class="desk-sub">{_esc(" · ".join(bits))}'
                + (f' · <span class="{due_cls}">{due_txt}</span>' if due_txt else "")
                + (f' · next: {_esc(next_txt[:70])}' if next_txt else "") + "</div></div>", unsafe_allow_html=True)
            try:
                fit = int(float(o.get("fit_score") or 0))
            except (TypeError, ValueError):
                fit = 0
            c2.markdown(f'<div class="desk-meta">{_esc(p_.get("owner_name") or p_.get("owner_email") or "") if _view == "Team" else ""}'
                        f'<span class="opp-tag">fit {fit}</span></div>', unsafe_allow_html=True)
            with c3:
                if st.button("Open" if sid != selected else "Opened", key=f"open_{_view}_{sid}", use_container_width=True,
                             type="primary" if sid == selected else "secondary", disabled=sid == selected):
                    st.session_state[sel_key] = sid
                    st.rerun()

    if selected:
        if st.query_params.get("open") != selected:
            st.query_params["open"] = selected  # the address bar is the share link for this pursuit
            st.session_state["desk_deeplink"] = selected  # our own update, not an incoming link: do not re-route the view
        p_ = next(p for _, p in ordered if p["source_id"] == selected)
        o = opps.get(selected)
        if o:
            st.markdown('<div class="desk-workspace"></div>', unsafe_allow_html=True)
            _render_pursuit_panel(o, p_, events.get(selected, []))

    closed = sorted(by_stage["closed"], key=lambda x: x.get("closed_at") or x.get("updated_at") or "", reverse=True)
    if closed:
        with st.expander(f"Closed · {len(closed)}"):
            from oppos.pursuits import reopen_pursuit
            st.caption("Won, lost, abandoned or put back. Reopen brings one back to Pursuing on your desk.")
            for p_ in closed[:50]:
                o = opps.get(p_["source_id"]) or {}
                when = str(p_.get("closed_at") or p_.get("updated_at") or "")[:10]
                r1, r2 = st.columns([6, 1], vertical_alignment="center")
                r1.markdown(f'<div class="pp-event">{_esc(when)} · <b>{_esc(stage_label(p_.get("status")))}</b> · '
                            f'{_esc(p_.get("owner_name") or p_.get("owner_email") or "")} — {_esc(o.get("title") or p_["source_id"])}</div>',
                            unsafe_allow_html=True)
                with r2:
                    if o and CURRENT_USER.get("can_work") and st.button("Reopen", key=f"reopen_closed_{p_['source_id']}", use_container_width=True):
                        reopen_pursuit(o, CURRENT_USER)
                        st.session_state["desk_selected_Mine"] = p_["source_id"]
                        st.session_state["pursuit_view"] = "Mine"
                        _flash(f"Reopened — {o.get('title', '')[:60]} is back in Pursuing", icon="↩️")
                        st.rerun()
            if len(closed) > 50:
                st.caption(f"{len(closed) - 50} older closed items not shown.")


def page_admin() -> None:
    """Admin — source health, portal registrations, settings."""
    from oppos.storage.db import get_source_health as _get_source_health
    _health_rows = [r for r in _get_source_health() if r.get("source") not in EXCLUDED_SOURCES]
    if _health_rows:
        _n_fail = sum(1 for r in _health_rows if r.get("last_error"))
        _health_label = "Source health" + (f"  ·  {_n_fail} failing" if _n_fail else "  ·  all OK")
        with st.expander(_health_label):
            st.markdown(_render_source_health(_health_rows), unsafe_allow_html=True)

    if CURRENT_USER.get("is_admin"):
        with st.expander(f"Settings  ·  {len(EXCLUDED_SOURCES)} source{'s' if len(EXCLUDED_SOURCES) != 1 else ''} excluded"):
            from oppos.storage.db import archive_sources, count_active_by_sources, list_sources_in_db, set_excluded_sources
            _db_sources = dict(list_sources_in_db())
            _all_keys = sorted(set(SOURCE_LABELS) | set(_db_sources) | EXCLUDED_SOURCES)
            def _src_label(k: str) -> str:
                base = SOURCE_LABELS.get(k, k)
                n = _db_sources.get(k)
                tag = "" if k in SOURCE_LABELS else " · retired"
                return f"{base}{tag}" + (f"  ({n} rows)" if n else "")
            st.markdown('<div class="detail-label" style="margin-bottom:6px;">Who can grab and work RFPs</div>', unsafe_allow_html=True)
            _stored = _cached_meta("members")
            _env_members = member_emails(None)
            try:
                _stored_list = [str(e) for e in json.loads(_stored)] if _stored else []
            except (TypeError, ValueError):
                _stored_list = []
            _members_txt = st.text_area("Member emails, one per line", value="\n".join(_stored_list), key="members_txt", height=120,
                                        placeholder="name@nutrient.io", label_visibility="collapsed")
            _all_members = member_emails(_stored)
            if not _all_members:
                st.warning("Access is open: anyone who signs in can grab and work RFPs. Add emails here to restrict it. Admins are always members.")
            else:
                st.caption(f"{len(_all_members)} member{'s' if len(_all_members) != 1 else ''} can grab and work RFPs"
                           + (f" ({len(_env_members)} from OPPOS_MEMBERS)" if _env_members else "") + "; everyone else can browse. Admins are always members.")
            if st.button("Save members", key="members_save"):
                _new = sorted({e.strip().lower() for e in _members_txt.splitlines() if e.strip()})
                set_meta("members", json.dumps(_new))
                _flash(f"Members saved — {len(_new)} listed")
                st.rerun()
            st.markdown('<div class="detail-label" style="margin:14px 0 6px;">Sources</div>', unsafe_allow_html=True)
            st.caption("Excluded sources are hidden from every list, skipped by scans, and never alerted. "
                       "Items you already claimed stay in your pursuits.")
            _sel = st.multiselect("Excluded sources", _all_keys, default=sorted(EXCLUDED_SOURCES),
                                  format_func=_src_label, key="excluded_sources_select")
            _sc1, _sc2 = st.columns([1, 2])
            with _sc1:
                if st.button("Save exclusions", key="excluded_save", use_container_width=True):
                    set_excluded_sources(_sel)
                    st.rerun()
            with _sc2:
                _n_active = count_active_by_sources(sorted(EXCLUDED_SOURCES)) if EXCLUDED_SOURCES else 0
                if _n_active:
                    with st.popover(f"Archive {_n_active} active item{'s' if _n_active != 1 else ''} from excluded sources",
                                    use_container_width=True):
                        st.write(f"Moves {_n_active} new / qualified / expiring items from "
                                 f"{', '.join(SOURCE_LABELS.get(k, k) for k in sorted(EXCLUDED_SOURCES))} to Archive (skipped) "
                                 "with the note \"Source excluded\". Pursuits are not touched. This cannot be undone in bulk.")
                        if st.button("Archive them", key="excluded_archive", type="primary", use_container_width=True):
                            _done = archive_sources(sorted(EXCLUDED_SOURCES))
                            st.success(f"Archived {_done} items")
                            st.rerun()
                elif EXCLUDED_SOURCES:
                    st.caption("No active items remain from excluded sources.")

        _reg_known = sum(1 for r in PORTAL_REGS.values() if (r.get("status") or "unknown") != "unknown")
        with st.expander(f"Portal registrations  ·  {_reg_known}/{len(PORTAL_REGS)} known"):
            import pandas as pd
            from oppos.pursuits import REGISTRATION_LABELS, REGISTRATION_STATUSES
            from oppos.storage.db import upsert_portal_registration

            _reg_cols = ["portal", "display_name", "status", "vendor_id", "login_owner", "lead_time_days", "url", "notes"]
            _reg_rows = [{c: r.get(c) for c in _reg_cols} for r in PORTAL_REGS.values()]
            _reg_df = pd.DataFrame(_reg_rows, columns=_reg_cols).sort_values("display_name", na_position="last").reset_index(drop=True)
            _reg_df["lead_time_days"] = pd.to_numeric(_reg_df["lead_time_days"], errors="coerce")
            _reg_df["status"] = _reg_df["status"].fillna("unknown")
            st.caption("Which procurement portals Nutrient is registered on, who holds the login, and how long registration takes. "
                       "Shown as a badge on every card and used in the pursuit checklist. Never store passwords here.")
            _edited = st.data_editor(
                _reg_df, hide_index=True, use_container_width=True, disabled=["portal", "display_name"], key="reg_editor",
                column_config={
                    "portal": st.column_config.TextColumn("Key"),
                    "display_name": st.column_config.TextColumn("Portal"),
                    "status": st.column_config.SelectboxColumn("Status", options=REGISTRATION_STATUSES, required=True),
                    "vendor_id": st.column_config.TextColumn("Vendor / supplier ID"),
                    "login_owner": st.column_config.TextColumn("Login held by"),
                    "lead_time_days": st.column_config.NumberColumn("Lead time (days)", min_value=0, step=1),
                    "url": st.column_config.LinkColumn("Registration URL"),
                    "notes": st.column_config.TextColumn("Notes"),
                },
            )
            if st.button("Save registrations", key="reg_save"):
                _changed = 0
                for _new, _old in zip(_edited.to_dict("records"), _reg_df.to_dict("records")):
                    def _clean(v):
                        return None if v is None or (isinstance(v, float) and pd.isna(v)) else v
                    _new_c = {k: _clean(v) for k, v in _new.items()}
                    _old_c = {k: _clean(v) for k, v in _old.items()}
                    if _new_c != _old_c:
                        _lead = _new_c.get("lead_time_days")
                        upsert_portal_registration(
                            _new_c["portal"], status=_new_c.get("status") or "unknown", vendor_id=_new_c.get("vendor_id"),
                            login_owner=_new_c.get("login_owner"), lead_time_days=int(_lead) if _lead is not None else None,
                            url=_new_c.get("url"), notes=_new_c.get("notes"),
                        )
                        _changed += 1
                st.success(f"Saved {_changed} change(s)")
                st.rerun()

    from oppos.drafting import compliance_status as _compliance_status
    _comp = _compliance_status()
    st.caption("Licences (set in the app's secrets / environment, never shown here): "
               f"Document Authoring {'set' if DOCAUTH_LICENSE_KEY else 'NOT set — response documents carry the evaluation watermark'} · "
               f"Web SDK viewer {'set' if VIEWER_LICENSE_KEY else 'not set — PDF preview carries the trial watermark'}")
    if CURRENT_USER.get("is_admin") and not (DOCAUTH_LICENSE_KEY and VIEWER_LICENSE_KEY):
        # Names only (never values): enough to spot a misspelt or nested secret from here.
        try:
            _names = []
            for _k in sorted(st.secrets.keys()):
                _v = st.secrets[_k]
                _names.append(f"{_k} (section: {', '.join(sorted(_v.keys()))})" if hasattr(_v, "keys") else _k)
            _seen = ", ".join(_names) or "none"
        except Exception as _e:
            _seen = f"no secrets file ({type(_e).__name__})"
        _env = ", ".join(sorted(k for k in os.environ if "LICENSE" in k.upper() or "LICENCE" in k.upper())) or "none"
        st.caption(f"Secrets visible to the app (names only): {_seen}. Environment variables with LICENSE in the name: {_env}. "
                   "The editor reads DOCAUTH_LICENSE_KEY and VIEWER_LICENSE_KEY at the top level, outside any [section].")
    st.caption("Compliance answers source (oppos/drafting/compliance.md): "
               + (f"approved v{_comp['version']} by {_comp['approved_by']} on {_comp['approved_at']}" if _comp["approved"]
                  else "NOT approved — response drafts mark every security/certification item [SECURITY TO CONFIRM] until the security team fills it in and sets approved: true."))
    if not CURRENT_USER.get("is_admin"):
        st.caption("Members, sources and portal registrations are managed by admins (OPPOS_ADMINS).")


_welcome()

_PAGE_POOL = st.Page(page_pool, title="Find RFPs", icon=":material/search:", default=True)  # served at /
_PAGE_DESK = st.Page(page_desk, title="My desk", icon=":material/person:", url_path="desk")
_PAGE_ADMIN = st.Page(page_admin, title="Admin", icon=":material/settings:", url_path="admin")
_nav = st.navigation(
    [_PAGE_POOL, _PAGE_DESK, _PAGE_ADMIN],
    position="top",
)
_nav.run()

st.markdown(f"""
<div class="oppos-footer">
    <span style="color: var(--text-secondary);">{NUTRIENT_DOTS_SVG}</span>
    <span>OppOS &middot; Automated RFP Intelligence</span>
</div>
""", unsafe_allow_html=True)
