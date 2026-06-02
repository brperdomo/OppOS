"""OppOS Streamlit dashboard.

Run with:
    streamlit run oppos/dashboard/app.py
"""

from __future__ import annotations

import json
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

from oppos.config import DB_PATH, SOURCE_STATE_MAP
from oppos.sources.registry import list_available
from oppos.storage.db import check_deadlines, get_all_scored, get_by_pipeline_status, get_meta, init_db, set_meta, set_pipeline_status

ATTACHMENTS_DIR = DB_PATH.parent / "attachments"

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

/* Hide default Streamlit header and footer */
#MainMenu, footer, header {visibility: hidden;}
.stDeployButton {display: none;}

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
    padding: 20px 0 16px 0;
    margin-bottom: 8px;
    border-bottom: 1px solid var(--border-subtle);
}
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

/* Empty state */
.empty-state {
    text-align: center;
    padding: 80px 24px;
    color: var(--text-tertiary);
}
.empty-state h3 {
    color: var(--text-secondary);
    font-weight: 600;
    margin-bottom: 8px;
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
</style>
"""

st.markdown(NUTRIENT_CSS, unsafe_allow_html=True)

NUTRIENT_DOTS_SVG = '<svg viewBox="0 0 50 36" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M4.15 22.15C1.86 22.15 0 20.29 0 18s1.86-4.15 4.15-4.15 4.15 1.86 4.15 4.15-1.86 4.15-4.15 4.15zm41.52-8.3c-2.29 0-4.15 1.86-4.15 4.15s1.86 4.15 4.15 4.15 4.15-1.86 4.15-4.15-1.86-4.15-4.15-4.15zM6.34 28.16c-1.76 1.47-1.99 4.09-.51 5.85s4.09 1.99 5.85.51 1.99-4.09.51-5.85-4.09-1.99-5.85-.51zm37.15-20.33c1.76-1.47 1.99-4.09.51-5.85s-4.09-1.99-5.85-.51-1.99 4.09-.51 5.85 4.09 1.99 5.85.51zM11.68 1.47C9.92 0 7.3.23 5.83 1.99s-.23 4.38 1.51 5.85 4.38.23 5.85-1.51.23-4.38-1.51-5.85zm31.81 26.69c-1.76-1.47-4.38-1.25-5.85.51s-1.25 4.38.51 5.85 4.38 1.25 5.85-.51 1.25-4.38-.51-5.85zm-10.6-8.9c-1.76-1.47-4.38-1.25-5.85.51s-1.25 4.38.51 5.85 4.38 1.25 5.85-.51 1.25-4.38-.51-5.85zm-10.6-8.9c-1.76-1.47-4.38-1.25-5.85.51s-1.25 4.38.51 5.85 4.38 1.25 5.85-.51 1.25-4.38-.51-5.85z" fill="currentColor"/></svg>'

NUTRIENT_WORDMARK_SVG = '<svg viewBox="60 0 148 36" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M83.25 4h3.56v28.09h-4.1L73.1 15.2c-.52-.94-1.6-3.04-3.25-6.3h-.04c.05 1.2.1 2.51.14 3.93.04 1.42.06 2.48.06 3.18v16.08h-3.56V4h4l9.64 16.69c.48.84 1.36 2.47 2.63 4.92l.7 1.35h.04c-.05-1.07-.1-2.3-.14-3.7-.04-1.4-.06-2.52-.06-3.37V4zm21.01 19.3c0 4.18-1.72 6.27-5.17 6.27-.77 0-1.44-.07-2.02-.21-.57-.14-1.12-.45-1.63-.95-.38-.36-.65-.78-.82-1.24-.17-.46-.27-.93-.3-1.39-.03-.46-.05-1.11-.05-1.95V12.04h-3.72v11.99c0 .94.03 1.76.09 2.45.06.69.21 1.38.44 2.07.23.69.59 1.28 1.08 1.79.72.77 1.56 1.34 2.52 1.7.97.36 2.1.55 3.41.55 1.44 0 2.69-.3 3.76-.9s1.87-1.5 2.41-2.63v3h3.6V12.04h-3.6v11.26zm14.42-16.85h-3.56v5.58h-4.21v3.02h4.21v12.1c0 1.82.49 3.13 1.47 3.93s2.56 1.2 4.74 1.2c.55 0 1.1-.03 1.64-.09.54-.06.99-.13 1.34-.22l-.08-3.29c-1.01.24-1.88.35-2.6.35-.73 0-1.35-.06-1.76-.17-.41-.11-.71-.31-.9-.6-.19-.29-.28-.7-.28-1.23V15.06h5.7v-3.02h-5.7V6.45zm16.05 6.52c-1.27.76-2.1 1.7-2.48 2.82V12.04h-3.6v20.06h3.6v-9.19c0-2.1.31-3.74.94-4.92.63-1.17 1.48-1.98 2.55-2.42 1.07-.44 2.37-.66 3.9-.66.61 0 1.03.02 1.25.06l.08-3.43c-.86 0-1.41.01-1.64.04-1.79.17-3.32.63-4.6 1.39zm35.56 5.62c.3 1.19.45 2.43.45 3.7 0 .38 0 .66-.02.84h-15.22c.04 2.21.53 3.85 1.47 4.93.94 1.08 2.35 1.62 4.23 1.62 1.7 0 3.02-.37 3.96-1.1.94-.74 1.53-1.87 1.78-3.38l3.49.27c-.45 2.34-1.45 4.11-3.01 5.31-1.56 1.2-3.62 1.8-6.18 1.8-3.08 0-5.48-.98-7.21-2.94-1.63-1.83-2.45-4.37-2.45-7.62 0-1.5.21-2.89.64-4.16.42-1.27 1.05-2.37 1.89-3.3.87-.99 1.91-1.74 3.12-2.25 1.2-.51 2.53-.76 3.97-.76 1.62 0 3.13.34 4.52 1.03 1.4.69 2.5 1.67 3.31 2.95.54.86.96 1.89 1.26 3.07zm-3.27 1.62c-.01-.57-.12-1.2-.31-1.87-.2-.67-.45-1.24-.77-1.7-.51-.76-1.15-1.31-1.91-1.66-.76-.35-1.69-.52-2.79-.52-1.1 0-2.06.19-2.88.58-.82.38-1.44.92-1.84 1.59-.34.55-.58 1.14-.73 1.76-.15.63-.24 1.23-.25 1.82h11.48zm23.66-4.61c-.23-.7-.58-1.3-1.05-1.81-.73-.77-1.58-1.34-2.55-1.7-.97-.36-2.11-.55-3.43-.55-3.07 0-5.13 1.19-6.19 3.56v-3.07h-3.6v20.06h3.6V21.03c0-2.52.54-4.23 1.63-5.12 1.08-.9 2.28-1.34 3.6-1.34.74 0 1.4.07 1.96.21.56.14 1.1.45 1.61.95.38.36.66.78.83 1.25.18.47.28.94.31 1.42.03.48.05 1.14.05 1.99v11.71h3.74v-11.9c0-.95-.03-1.78-.09-2.48-.06-.7-.2-1.4-.43-2.1zm16.67-.56v-3.02h-5.7V6.45h-3.56v5.58h-4.21v3.02h4.21v12.1c0 1.82.49 3.13 1.47 3.93s2.56 1.2 4.74 1.2c.55 0 1.1-.03 1.64-.09.54-.06.99-.13 1.34-.22l-.08-3.29c-1.01.24-1.88.35-2.6.35-.73 0-1.35-.06-1.76-.17-.41-.11-.71-.31-.9-.6-.19-.29-.28-.7-.28-1.23V15.06h5.7zm-62.78 17.07h3.6V12.06h-3.6v20.06zm1.8-28.71c-1.45 0-2.63 1.18-2.63 2.63s1.18 2.63 2.63 2.63 2.63-1.18 2.63-2.63-1.18-2.63-2.63-2.63z" fill="currentColor"/></svg>'

st.markdown(f"""
<div class="oppos-header">
    <div class="oppos-header-left">
        <div class="nutrient-logo-mark" style="color: var(--accent-gold);">{NUTRIENT_DOTS_SVG}</div>
        <div>
            <h1>OppOS</h1>
            <div class="subtitle">RFP Opportunity Pipeline</div>
        </div>
    </div>
    <div class="nutrient-brand" style="color: var(--text-secondary);">{NUTRIENT_WORDMARK_SVG}</div>
</div>
""", unsafe_allow_html=True)

init_db()
check_deadlines()  # Auto-move expired / expiring-soon RFPs on every page load
SOURCE_LABELS = dict(list_available())
SOURCE_LABELS["manual"] = "Manual Submission"

PIPELINE_LABELS = {
    "new": "New",
    "qualified": "Qualified",
    "expiring_soon": "Expiring Soon",
    "in_progress": "In Progress",
    "submitted": "Submitted",
    "won": "Won",
    "lost": "Lost",
    "skipped": "Skipped",
    "expired": "Expired",
}

STATUS_OPTIONS = list(PIPELINE_LABELS.keys())
STATUS_DISPLAY = list(PIPELINE_LABELS.values())


def _run_scan() -> dict:
    """Run the pipeline in-process and return stats."""
    import logging
    from oppos.config import STAGE2_MIN_SCORE
    from oppos.scoring.prefilter import prefilter
    from oppos.scoring.qualifier import qualify
    from oppos.sources.registry import get_enabled_sources
    from oppos.storage.db import is_seen, set_meta as _set_meta, upsert_opportunity

    logging.basicConfig(level=logging.INFO)
    sources = get_enabled_sources()
    stats = {"fetched": 0, "new": 0, "filtered_out": 0, "scored": 0, "errors": []}
    posted_from = datetime.now() - timedelta(days=14)

    for key, name, fetch_fn in sources:
        try:
            opps = fetch_fn(posted_from=posted_from) if key == "sam_gov" else fetch_fn()
            stats["fetched"] += len(opps)
            for opp in opps:
                if is_seen(opp["source_id"]):
                    continue
                stats["new"] += 1
                # Rules-based pre-filter — skip obvious non-software
                prefilter(opp)
                if not opp["prefilter"]["passed"]:
                    stats["filtered_out"] += 1
                    continue
                scored = qualify(opp)
                if scored.get("fit_score", 0) >= STAGE2_MIN_SCORE:
                    stats["scored"] += 1
                upsert_opportunity(scored)
        except Exception as e:
            stats["errors"].append(f"{name}: {e}")

    # Record scan timestamp
    _set_meta("last_scan", datetime.utcnow().isoformat())

    return stats


# --- Scan button row ---
scan_col, manual_col = st.columns([1, 1])
with scan_col:
    scan_clicked = st.button("Scan for New RFPs", use_container_width=True, type="primary")
    # Show last scan timestamp
    _last_scan_raw = get_meta("last_scan")
    if _last_scan_raw:
        try:
            _last_scan_dt = datetime.fromisoformat(_last_scan_raw).replace(tzinfo=timezone.utc)
            _now_utc = datetime.now(timezone.utc)
            _delta = _now_utc - _last_scan_dt
            if _delta.total_seconds() < 60:
                _ago = "just now"
            elif _delta.total_seconds() < 3600:
                _mins = int(_delta.total_seconds() // 60)
                _ago = f"{_mins}m ago"
            elif _delta.total_seconds() < 86400:
                _hrs = int(_delta.total_seconds() // 3600)
                _ago = f"{_hrs}h ago"
            else:
                _days = int(_delta.days)
                _ago = f"{_days}d ago"
            _local_str = _last_scan_dt.astimezone().strftime("%-m/%-d %I:%M %p")
            st.caption(f"Last scan: {_local_str} ({_ago})")
        except Exception:
            st.caption(f"Last scan: {_last_scan_raw}")
with manual_col:
    manual_open = st.button("Submit Manual RFP", use_container_width=True)

if manual_open:
    st.session_state["show_manual_form"] = True

if scan_clicked:
    with st.spinner("Scanning all sources for new opportunities..."):
        scan_stats = _run_scan()
    filtered = scan_stats.get("filtered_out", 0)
    if scan_stats["new"] > 0:
        filter_note = f" · {filtered} non-software filtered out" if filtered else ""
        st.markdown(f"""
        <div class="scan-result">
            Found <strong>{scan_stats["new"]} new</strong> opportunities
            ({scan_stats["scored"]} scored above threshold{filter_note})
            from {scan_stats["fetched"]} total listings scanned.
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div class="scan-result no-new">
            No new opportunities found. Scanned {scan_stats["fetched"]} listings across all sources.
        </div>
        """, unsafe_allow_html=True)
    if scan_stats["errors"]:
        with st.expander(f"{len(scan_stats['errors'])} source(s) had errors"):
            for err in scan_stats["errors"]:
                st.text(err)
    st.rerun()

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


if st.session_state.get("show_manual_form"):
    with st.container():
        st.markdown(
            '<div style="border: 1px solid var(--border-subtle); border-radius: 8px; padding: 16px; margin-bottom: 16px;">',
            unsafe_allow_html=True,
        )
        st.markdown("#### Submit Manual RFP")
        st.markdown(
            '<div style="font-size: 13px; color: var(--text-tertiary); margin-bottom: 12px;">'
            "Paste a link to any RFP page or upload a PDF/DOCX directly. "
            "The system will extract metadata, download attachments, and score it through the same AI pipeline.</div>",
            unsafe_allow_html=True,
        )

        url_tab, file_tab = st.tabs(["Paste URL", "Upload File"])

        with url_tab:
            manual_url = st.text_input(
                "RFP URL",
                key="manual_url_input",
                placeholder="https://procurement.example.com/rfp/12345",
            )
            url_submit = st.button("Analyze URL", key="manual_url_submit", use_container_width=True)
            if url_submit and manual_url:
                with st.status("Analyzing RFP...", expanded=True) as status:
                    result = _run_manual_url(manual_url)
                    if result.get("error"):
                        status.update(label=f"Failed: {result['error']}", state="error")
                    else:
                        score = result.get("fit_score", 0)
                        title = result.get("title", "Untitled")
                        status.update(label=f"Score: {score}/100 — {title[:50]}", state="complete")
                # Persist result so it survives reruns
                st.session_state["manual_result"] = result
                if result.get("_att_files"):
                    sid = result.get("source_id", "")
                    st.session_state[f"att_files_{sid}"] = result["_att_files"]

        with file_tab:
            uploaded = st.file_uploader(
                "Upload PDF or DOCX",
                type=["pdf", "docx"],
                key="manual_file_upload",
            )
            file_submit = st.button("Analyze File", key="manual_file_submit", use_container_width=True)
            if file_submit and uploaded:
                file_bytes = uploaded.read()
                with st.status(f"Analyzing {uploaded.name}...", expanded=True) as status:
                    result = _run_manual_file(file_bytes, uploaded.name)
                    if result.get("error"):
                        status.update(label=f"Failed: {result['error']}", state="error")
                    else:
                        score = result.get("fit_score", 0)
                        title = result.get("title", "Untitled")
                        status.update(label=f"Score: {score}/100 — {title[:50]}", state="complete")
                st.session_state["manual_result"] = result
                if result.get("_att_files"):
                    sid = result.get("source_id", "")
                    st.session_state[f"att_files_{sid}"] = result["_att_files"]

        # --- Persistent result display (survives reruns) ---
        manual_result = st.session_state.get("manual_result")
        if manual_result:
            if manual_result.get("error"):
                st.error(f"Could not process: {manual_result['error']}")
            else:
                score = manual_result.get("fit_score", 0)
                title = manual_result.get("title", "Untitled")
                agency = manual_result.get("agency", "")
                s2 = manual_result.get("stage2") or {}

                st.success(f"Added to Pipeline — **{title}** scored **{score}/100**")

                with st.expander("Analysis Details", expanded=True):
                    if agency:
                        st.write(f"**Agency:** {agency}")
                    st.write(f"**Score:** {score}/100 — {manual_result.get('recommended_action', '?')}")
                    if s2.get("summary"):
                        st.write(f"_{s2['summary']}_")
                    if s2.get("strengths"):
                        st.write("**Strengths:** " + " · ".join(s2["strengths"][:3]))
                    if s2.get("risks"):
                        st.write("**Risks:** " + " · ".join(s2["risks"][:3]))

        # Close / clear
        if st.button("Close", key="manual_cancel"):
            st.session_state["show_manual_form"] = False
            st.session_state.pop("manual_result", None)
            st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

all_rows = get_all_scored(min_score=0)

status_counts = {}
for s in PIPELINE_LABELS:
    status_counts[s] = sum(1 for r in all_rows if (r.get("pipeline_status") or "new") == s)

high_fit = sum(1 for r in all_rows if int(r.get("fit_score") or 0) >= 65)

st.markdown(f"""
<div class="stats-bar">
    <div class="stat-item">
        <div class="stat-value">{len(all_rows)}</div>
        <div class="stat-label">Total Reviewed</div>
    </div>
    <div class="stat-item">
        <div class="stat-value green">{high_fit}</div>
        <div class="stat-label">High Fit (65+)</div>
    </div>
    <div class="stat-item">
        <div class="stat-value" style="color: var(--accent-orange);">{status_counts.get('expiring_soon', 0)}</div>
        <div class="stat-label">Expiring</div>
    </div>
    <div class="stat-item">
        <div class="stat-value gold">{status_counts.get('in_progress', 0)}</div>
        <div class="stat-label">In Progress</div>
    </div>
    <div class="stat-item">
        <div class="stat-value green">{status_counts.get('submitted', 0)}</div>
        <div class="stat-label">Submitted</div>
    </div>
    <div class="stat-item">
        <div class="stat-value pink">{status_counts.get('won', 0)}</div>
        <div class="stat-label">Won</div>
    </div>
</div>
""", unsafe_allow_html=True)

_expiring_count = status_counts.get('expiring_soon', 0)
_expired_count = status_counts.get('expired', 0)
_archive_count = status_counts.get('won', 0) + status_counts.get('lost', 0) + status_counts.get('skipped', 0)

tab_pipeline, tab_qualified, tab_expiring, tab_in_progress, tab_submitted, tab_archive, tab_expired = st.tabs([
    f"Pipeline ({status_counts.get('new', 0)})",
    f"Qualified ({status_counts.get('qualified', 0)})",
    f"Expiring Soon ({_expiring_count})" if _expiring_count else "Expiring Soon",
    f"In Progress ({status_counts.get('in_progress', 0)})",
    f"Submitted ({status_counts.get('submitted', 0)})",
    f"Archive ({_archive_count})",
    f"Expired ({_expired_count})" if _expired_count else "Expired",
])


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
    """Full Pursue flow: Notion push → Slack alert (with Notion link) → status update."""
    from oppos.outputs.notion_sync import push_opportunity
    from oppos.outputs.slack_alerts import send_pursue_alert
    from oppos.storage.db import set_notion_page_id, upsert_opportunity

    sid = opp.get("source_id", "")
    title = opp.get("title", "Untitled")

    with st.status(f"Pursuing: {title[:50]}…", expanded=True) as status:
        # Step 1: Push to Notion
        notion_url = ""
        st.write("📤 Pushing to Notion…")
        try:
            # Set status before push so Notion shows "In Progress"
            opp["pipeline_status"] = "in_progress"
            opp["pipeline_notes"] = reason or "Qualified — pursuing"

            att_dir = ATTACHMENTS_DIR / sid
            att_paths = sorted(att_dir.glob("*")) if att_dir.exists() else []
            page_id = push_opportunity(opp, attachment_paths=att_paths or None)
            if page_id:
                set_notion_page_id(sid, page_id)
                notion_url = f"https://notion.so/{page_id.replace('-', '')}"
                st.write(f"✓ Notion page created — [Open]({notion_url})")
            else:
                st.write("⚠️ Notion push failed — continuing with Slack…")
        except Exception as e:
            st.write(f"⚠️ Notion error: {e} — continuing with Slack…")

        # Step 2: Update pipeline status
        st.write("📋 Updating pipeline status…")
        set_pipeline_status(sid, "in_progress", notes=reason or "Qualified — pursuing")

        # Step 3: Send Slack alert with Notion link
        st.write("📣 Sending Slack alert…")
        send_pursue_alert(opp, reason=reason, notion_url=notion_url)

        status.update(label="Pursuing ✓", state="complete")
        st.success(f"**{title[:60]}** moved to In Progress" + (f" — [Notion]({notion_url})" if notion_url else ""))


def _push_to_notion(opp: dict) -> None:
    """Push an opportunity to the Notion RFP Pipeline database."""
    from oppos.outputs.notion_sync import push_opportunity
    from oppos.storage.db import set_notion_page_id

    sid = opp.get("source_id", "")
    title = opp.get("title", "Untitled")

    with st.status(f"Pushing to Notion: {title[:50]}…", expanded=True) as status:
        st.write("📤 Sending RFP data, scanned documents, and capability profile…")

        # Collect attachment files if they exist on disk
        att_dir = ATTACHMENTS_DIR / sid
        attachment_paths = sorted(att_dir.glob("*")) if att_dir.exists() else []
        if attachment_paths:
            st.write(f"📎 {len(attachment_paths)} attachment(s) will be uploaded")

        try:
            page_id = push_opportunity(opp, attachment_paths=attachment_paths or None)
            if page_id:
                set_notion_page_id(sid, page_id)
                clean_id = page_id.replace("-", "")
                status.update(label="Pushed to Notion ✓", state="complete")
                st.success(f"Page created — [Open in Notion](https://notion.so/{clean_id})")
            else:
                status.update(label="Notion push failed", state="error")
                st.error("Push failed — check that NOTION_TOKEN and NOTION_DATABASE_ID are set.")
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
            st.write("**Strengths:** " + " · ".join(s2["strengths"]))
        if s2.get("risks"):
            st.write("**Risks:** " + " · ".join(s2["risks"]))
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


def _render_deep_scan(opp: dict, tab_key: str) -> None:
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
        st.markdown(
            '<div style="font-size: 12px; color: var(--text-tertiary); padding-top: 8px;">'
            'Download and list all attachments — choose which files to scan</div>',
            unsafe_allow_html=True,
        )

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
                _run_ocr_and_score(opp, selected, tab_key)
        elif scannable and not any(f.name not in scanned_files for f in scannable):
            _rescore_col1, _rescore_col2 = st.columns([1, 3])
            with _rescore_col1:
                if st.button("Re-Score", key=f"rescore_{tab_key}_{sid}", use_container_width=True):
                    _run_ocr_and_score(opp, scannable, tab_key)
            with _rescore_col2:
                st.markdown(
                    '<div style="font-size: 12px; color: var(--text-tertiary); padding-top: 8px;">'
                    'All files scanned — re-score with existing text to update fit score</div>',
                    unsafe_allow_html=True,
                )


def render_card(opp: dict, tab_key: str, show_status_controls: bool = True) -> None:
    s2_raw = opp.get("stage2_json")
    s2 = {}
    if s2_raw:
        try:
            s2 = json.loads(s2_raw) if isinstance(s2_raw, str) else s2_raw
        except (json.JSONDecodeError, TypeError):
            pass

    sid = opp.get("source_id", "")
    score = int(opp.get("fit_score") or 0)
    title = _esc(opp.get("title", "Untitled"))
    agency = _esc(opp.get("agency", "Unknown"))
    deadline = opp.get("response_deadline", "")
    deadline_display = deadline[:10] if deadline else "TBD"
    url = opp.get("url", "")
    sol_num = _esc(opp.get("solicitation_number", ""))
    source_label = _esc(SOURCE_LABELS.get(opp.get("source", ""), opp.get("source", "")))
    pipeline_status = opp.get("pipeline_status") or "new"
    pipeline_notes = opp.get("pipeline_notes") or ""
    assigned = opp.get("assigned_to") or ""

    # Compute deadline urgency for tag styling
    _deadline_css = "deadline"
    _deadline_prefix = "Due"
    if deadline:
        from oppos.storage.db import _parse_deadline
        _dl_dt = _parse_deadline(deadline)
        if _dl_dt:
            if _dl_dt.tzinfo is not None:
                _dl_dt = _dl_dt.replace(tzinfo=None)
            _days_left = (_dl_dt - datetime.utcnow()).total_seconds() / 86400
            if _days_left < 0:
                _deadline_css = "deadline-expired"
                _deadline_prefix = "EXPIRED"
            elif _days_left <= 3:
                _deadline_css = "deadline-urgent"
                _deadline_prefix = f"Due in {max(0, int(_days_left))}d"
            elif _days_left <= 7:
                _deadline_css = "deadline-urgent"
                _deadline_prefix = f"Due in {int(_days_left)}d"

    title_html = f'<a class="opp-title" href="{_esc(url)}" target="_blank">{title}</a>' if url else f'<span class="opp-title">{title}</span>'
    state_name = _esc(SOURCE_STATE_MAP.get(opp.get("source", ""), ""))

    is_new = False
    created = opp.get("created_at")
    if created:
        try:
            created_dt = datetime.fromisoformat(created)
            is_new = (datetime.now(timezone.utc) - created_dt.replace(tzinfo=timezone.utc)) < timedelta(hours=24)
        except (ValueError, TypeError):
            pass
    new_badge_html = '<span class="new-badge">NEW</span>' if is_new else ''

    status_label = PIPELINE_LABELS.get(pipeline_status, pipeline_status)

    score_card_class = "score-high-card" if score >= 65 else ("score-mid-card" if score >= 40 else "score-low-card")
    pattern = _esc(s2.get("pattern_match", "") or "")
    pattern_tag = f'<span class="opp-tag">{pattern}</span>' if pattern and pattern != "other" else ""
    sol_tag = f'<span class="opp-tag">{sol_num}</span>' if sol_num else ""

    card_parts = [
        f'<div class="opp-card {score_card_class}">',
        '<div class="opp-card-header">',
        '<div style="flex: 1;">',
        f'{new_badge_html} {title_html}',
        f'<div class="opp-subtitle"><strong>{state_name}</strong> &middot; {agency}</div>',
        '<div class="opp-meta">',
        f'<span class="pipeline-badge pipeline-{pipeline_status}">{status_label}</span>',
        f'<span class="opp-tag source">{source_label}</span>',
        sol_tag,
        f'<span class="opp-tag {_deadline_css}">{_deadline_prefix} {deadline_display}</span>',
        pattern_tag,
        '</div></div>',
        f'<div class="score-badge {_score_class(score)}">',
        f'<div class="score-number">{score}</div>',
        '<div class="score-label">Fit</div>',
        '</div></div>',
    ]

    summary_text = s2.get("summary", "")
    if summary_text:
        card_parts.append(f'<div class="opp-summary">{_esc(summary_text)}</div>')

    card_parts.append('</div>')

    st.markdown("\n".join(card_parts), unsafe_allow_html=True)

    if show_status_controls:
        with st.expander("Update Status"):
            sc1, sc2, sc3 = st.columns([2, 2, 1])
            with sc1:
                new_status = st.selectbox(
                    "Status",
                    STATUS_OPTIONS,
                    index=STATUS_OPTIONS.index(pipeline_status) if pipeline_status in STATUS_OPTIONS else 0,
                    format_func=lambda x: PIPELINE_LABELS.get(x, x),
                    key=f"status_{tab_key}_{sid}",
                )
            with sc2:
                new_notes = st.text_input(
                    "Notes",
                    value=pipeline_notes,
                    placeholder="e.g., Drafting response, waiting on compliance...",
                    key=f"notes_{tab_key}_{sid}",
                )
            with sc3:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("Save", key=f"save_{tab_key}_{sid}", use_container_width=True):
                    # If moving to in_progress, trigger full Pursue flow (Notion + Slack)
                    if new_status == "in_progress" and pipeline_status != "in_progress":
                        _pursue_opportunity(opp, reason=new_notes or "")
                    else:
                        set_pipeline_status(sid, new_status, notes=new_notes)
                        # Send Slack abandon alert when skipping/losing an in-progress item
                        if pipeline_status == "in_progress" and new_status in ("skipped", "lost"):
                            from oppos.outputs.slack_alerts import send_abandon_alert
                            _label = "Abandoned" if new_status == "lost" else "Skipped"
                            send_abandon_alert(opp, reason=new_notes or "", label=_label)
                    st.rerun()

    with st.expander("Details & Contact"):
        dc1, dc2 = st.columns(2)
        with dc1:
            c_name = opp.get("contact_name") or ""
            c_email = opp.get("contact_email") or ""
            c_phone = opp.get("contact_phone") or ""
            pop = opp.get("place_of_performance") or ""
            office = opp.get("office") or ""

            contact_html = ""
            if c_name:
                contact_html += f'<div class="contact-row">{_esc(c_name)}</div>'
            if c_email:
                contact_html += f'<div class="contact-row"><a href="mailto:{_esc(c_email)}">{_esc(c_email)}</a></div>'
            if c_phone:
                contact_html += f'<div class="contact-row">{_esc(c_phone)}</div>'
            if not (c_name or c_email or c_phone):
                contact_html = '<div class="contact-row" style="color: var(--text-tertiary);">Not provided</div>'

            st.markdown(f"""
            <div class="detail-label" style="margin-bottom: 8px;">Contact</div>
            {contact_html}
            """, unsafe_allow_html=True)

            info_html = ""
            if pop:
                info_html += f'<div class="detail-item"><div class="detail-label">Location</div><div class="detail-value">{_esc(pop)}</div></div>'
            if office:
                info_html += f'<div class="detail-item"><div class="detail-label">Office</div><div class="detail-value">{_esc(office)}</div></div>'
            naics = opp.get("naics_code") or ""
            set_aside = opp.get("set_aside") or ""
            if naics:
                info_html += f'<div class="detail-item"><div class="detail-label">NAICS</div><div class="detail-value">{_esc(naics)}</div></div>'
            if set_aside:
                info_html += f'<div class="detail-item"><div class="detail-label">Set-aside</div><div class="detail-value">{_esc(set_aside)}</div></div>'
            if info_html:
                st.markdown(f'<div style="display:flex;flex-direction:column;gap:8px;margin-top:12px;">{info_html}</div>', unsafe_allow_html=True)

        with dc2:
            posted = opp.get("posted_date")
            st.markdown(f"""
            <div class="detail-label" style="margin-bottom: 8px;">Key Dates</div>
            <div class="detail-value">Posted: {posted[:10] if posted else 'Unknown'}</div>
            <div class="detail-value" style="font-weight:600;">Deadline: {deadline_display}</div>
            """, unsafe_allow_html=True)

            desc = opp.get("description") or ""
            if desc:
                st.markdown(f"""
                <div class="detail-label" style="margin-top:16px;margin-bottom:8px;">Description</div>
                <div class="detail-value" style="line-height:1.6;">{_esc(desc[:2000])}</div>
                """, unsafe_allow_html=True)

    _has_assessment = bool(s2.get("summary") or s2.get("strengths") or s2.get("risks"))

    # Parse stage1 data for rejection reason display
    _s1_raw = opp.get("stage1_json")
    _s1 = {}
    if _s1_raw:
        try:
            _s1 = json.loads(_s1_raw) if isinstance(_s1_raw, str) else _s1_raw
        except (json.JSONDecodeError, TypeError):
            pass
    _was_filtered = bool(_s1 and not _s1.get("relevant") and not s2)

    with st.expander("AI Assessment", expanded=_has_assessment or _was_filtered):
        # Show stage1 rejection when stage2 was skipped
        if _was_filtered:
            _s1_reason = _s1.get("reason", "No reason provided")
            _s1_conf = _s1.get("confidence", 0)
            st.markdown(
                f'<div style="background: rgba(242, 95, 69, 0.1); border: 1px solid rgba(242, 95, 69, 0.3); '
                f'border-radius: 8px; padding: 12px; margin-bottom: 12px;">'
                f'<div style="font-weight: 600; color: var(--accent-red); margin-bottom: 4px;">'
                f'Stage 1 Filter: Not Relevant (confidence: {_s1_conf:.0%})</div>'
                f'<div style="color: var(--text-secondary); font-size: 13px;">{_esc(_s1_reason)}</div>'
                f'<div style="color: var(--text-tertiary); font-size: 11px; margin-top: 6px;">'
                f'Stage 2 deep scoring was skipped. Use "Force Score" to override and run full analysis.</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
        elif not s2 and not _s1:
            st.markdown(
                '<div style="color: var(--text-tertiary); font-size: 13px;">'
                'Not yet scored. Use "Score This" or batch scoring to run AI analysis.</div>',
                unsafe_allow_html=True,
            )

        detail_items = []
        if s2.get("pattern_match") and s2["pattern_match"] != "other":
            detail_items.append(("Pattern", s2["pattern_match"]))
        if s2.get("industry"):
            detail_items.append(("Industry", s2["industry"]))
        if s2.get("similar_win"):
            detail_items.append(("Similar Win", s2["similar_win"]))
        if opp.get("notice_type"):
            detail_items.append(("Notice Type", opp["notice_type"]))

        if detail_items:
            grid_html = "".join(
                f'<div class="detail-item"><div class="detail-label">{_esc(lbl)}</div><div class="detail-value">{_esc(val)}</div></div>'
                for lbl, val in detail_items
            )
            st.markdown(f'<div class="detail-grid">{grid_html}</div>', unsafe_allow_html=True)

        col_s, col_r = st.columns(2)
        with col_s:
            strengths = s2.get("strengths", [])
            if strengths:
                st.markdown('<div class="detail-label" style="margin-bottom:8px;margin-top:12px;">Strengths</div>', unsafe_allow_html=True)
                for s in strengths:
                    st.markdown(f'<div class="strength-item">+ {_esc(s)}</div>', unsafe_allow_html=True)
        with col_r:
            risks = s2.get("risks", [])
            if risks:
                st.markdown('<div class="detail-label" style="margin-bottom:8px;margin-top:12px;">Risks</div>', unsafe_allow_html=True)
                for r in risks:
                    st.markdown(f'<div class="risk-item">- {_esc(r)}</div>', unsafe_allow_html=True)

        if s2.get("deployment_recommendation"):
            st.markdown(f"""
            <div style="margin-top:12px;">
                <div class="detail-label">Deployment</div>
                <div class="detail-value">{_esc(s2['deployment_recommendation'])}</div>
            </div>
            """, unsafe_allow_html=True)
        if s2.get("competitive_notes"):
            st.markdown(f"""
            <div style="margin-top:8px;">
                <div class="detail-label">Competitive</div>
                <div class="detail-value">{_esc(s2['competitive_notes'])}</div>
            </div>
            """, unsafe_allow_html=True)

    # --- Deep Scan ---
    _render_deep_scan(opp, tab_key)

    att_dir = ATTACHMENTS_DIR / opp.get("source_id", "")
    if att_dir.is_dir():
        files = sorted(att_dir.iterdir())
        if files:
            with st.expander(f"Attachments ({len(files)})"):
                for f in files:
                    with open(f, "rb") as fh:
                        st.download_button(
                            f"{f.name}",
                            data=fh.read(),
                            file_name=f.name,
                            key=f"dl_{tab_key}_{sid}_{f.name}",
                        )


def render_empty(message: str) -> None:
    st.markdown(f"""
    <div class="empty-state">
        <h3>{message}</h3>
    </div>
    """, unsafe_allow_html=True)


# --- Pipeline tab (new opportunities) ---
with tab_pipeline:
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        min_score = st.slider("Min Score", 0, 100, 40, step=5, key="pipe_score")
    with col_f2:
        sort_by = st.selectbox("Sort by", ["Fit Score", "Deadline", "Posted"], key="pipe_sort")
    with col_f3:
        source_filter = st.multiselect(
            "Source",
            list(SOURCE_LABELS.keys()),
            format_func=lambda k: SOURCE_LABELS.get(k, k),
            key="pipe_source",
        )

    rows = get_all_scored(min_score=min_score)
    rows = [r for r in rows if (r.get("pipeline_status") or "new") == "new"]

    if source_filter:
        rows = [r for r in rows if r.get("source") in source_filter]

    if sort_by == "Deadline":
        rows.sort(key=lambda r: r.get("response_deadline") or "9999")
    elif sort_by == "Posted":
        rows.sort(key=lambda r: r.get("posted_date") or "", reverse=True)

    st.markdown(f'<div style="color: var(--text-tertiary); font-size: 14px; margin-bottom: 16px;"><strong>{len(rows)}</strong> new opportunities</div>', unsafe_allow_html=True)

    if not rows:
        render_empty("No new opportunities matching filters")
    for opp in rows:
        render_card(opp, "pipe")

# --- Qualified tab ---
with tab_qualified:
    qual_rows = get_by_pipeline_status("qualified")
    st.markdown(
        f'<div style="color: var(--text-tertiary); font-size: 14px; margin-bottom: 16px;">'
        f'<strong>{len(qual_rows)}</strong> scanned &amp; scored — ready for your decision</div>',
        unsafe_allow_html=True,
    )

    if not qual_rows:
        render_empty("No qualified RFPs yet. Deep Scan an opportunity from the Pipeline tab to move it here.")
    for opp in qual_rows:
        render_card(opp, "qual", show_status_controls=False)
        qsid = opp.get("source_id", "")
        qc1, qc2 = st.columns(2)
        with qc1:
            with st.popover("Pursue →", use_container_width=True):
                pursue_reason = st.text_input(
                    "Why are we pursuing this?",
                    key=f"pursue_reason_{qsid}",
                    placeholder="Strong fit for case management, aligns with public sector push",
                )
                if st.button("Confirm Pursue", key=f"confirm_pursue_{qsid}", use_container_width=True):
                    _pursue_opportunity(opp, reason=pursue_reason or "")
                    st.rerun()
        with qc2:
            with st.popover("Skip →", use_container_width=True):
                skip_reason = st.text_input(
                    "Reason for skipping?",
                    key=f"skip_reason_{qsid}",
                    placeholder="Not a workflow fit — pure staffing RFP",
                )
                if st.button("Confirm Skip", key=f"confirm_skip_{qsid}", use_container_width=True):
                    from oppos.outputs.slack_alerts import send_abandon_alert
                    set_pipeline_status(qsid, "skipped", notes=skip_reason or "Skipped after qualification review")
                    send_abandon_alert(opp, reason=skip_reason or "Skipped after qualification review", label="Skipped")
                    st.rerun()
        st.markdown("---")

# --- Expiring Soon tab ---
with tab_expiring:
    exp_rows = get_by_pipeline_status("expiring_soon")
    exp_rows.sort(key=lambda r: r.get("response_deadline") or "9999")

    _unscored_exp = [r for r in exp_rows if int(r.get("fit_score") or 0) == 0]
    _scored_exp = [r for r in exp_rows if int(r.get("fit_score") or 0) > 0]

    st.markdown(
        f'<div style="color: var(--accent-orange); font-size: 14px; margin-bottom: 16px;">'
        f'<strong>{len(exp_rows)}</strong> opportunities expiring within 7 days'
        f'{f" — <strong>{len(_unscored_exp)}</strong> unscored" if _unscored_exp else ""}'
        f'</div>',
        unsafe_allow_html=True,
    )

    # --- Batch scoring controls ---
    if _unscored_exp:
        def _score_batch(batch: list[dict], label: str) -> None:
            """Score a batch of opportunities — skips Stage 1, goes straight to deep scoring."""
            from oppos.scoring.qualifier import force_score
            from oppos.storage.db import upsert_opportunity

            progress = st.progress(0, text=f"Scoring {label}...")
            results = []
            for i, opp in enumerate(batch):
                title = opp.get("title", "Untitled")[:50]
                progress.progress(
                    (i) / len(batch),
                    text=f"Scoring {i+1}/{len(batch)}: {title}...",
                )
                try:
                    att_text = opp.get("attachment_text") or ""
                    scored = force_score(opp, attachment_text=att_text)
                    scored["attachment_text"] = att_text or None
                    upsert_opportunity(scored)
                    set_pipeline_status(
                        opp["source_id"], "expiring_soon",
                        notes=f"Scored from description — {scored.get('fit_score', 0)}/100",
                    )
                    results.append((title, scored.get("fit_score", 0), None))
                except Exception as e:
                    results.append((title, 0, str(e)))

            progress.progress(1.0, text="Done!")

            # Show results summary
            ok = [r for r in results if r[2] is None]
            errs = [r for r in results if r[2] is not None]
            if ok:
                avg = sum(r[1] for r in ok) / len(ok)
                high = sum(1 for r in ok if r[1] >= 65)
                st.success(f"Scored {len(ok)} RFPs — avg {avg:.0f}/100, {high} high-fit (65+)")
            if errs:
                st.warning(f"{len(errs)} failed: {', '.join(r[0] for r in errs)}")

        batch_size = 10
        total_unscored = len(_unscored_exp)
        bc1, bc2, bc3 = st.columns([1, 1, 2])
        with bc1:
            if st.button(
                f"Score Next {min(batch_size, total_unscored)}",
                key="exp_score_batch",
                use_container_width=True,
            ):
                _score_batch(_unscored_exp[:batch_size], f"next {min(batch_size, total_unscored)}")
                st.rerun()
        with bc2:
            if total_unscored > batch_size:
                if st.button(
                    f"Score All {total_unscored}",
                    key="exp_score_all",
                    use_container_width=True,
                ):
                    _score_batch(_unscored_exp, f"all {total_unscored}")
                    st.rerun()
        with bc3:
            st.markdown(
                '<div style="font-size: 12px; color: var(--text-tertiary); padding-top: 8px;">'
                'AI-score using RFP description — no documents needed</div>',
                unsafe_allow_html=True,
            )
        st.markdown("---")

    if not exp_rows:
        render_empty("No expiring opportunities. Deadlines are checked automatically on each page load.")
    for opp in exp_rows:
        render_card(opp, "exp")
        esid = opp.get("source_id", "")
        _opp_score = int(opp.get("fit_score") or 0)

        # Individual score button for unscored opps
        if _opp_score == 0:
            if st.button("Score This", key=f"exp_score_{esid}"):
                from oppos.scoring.qualifier import force_score
                from oppos.storage.db import upsert_opportunity
                with st.spinner(f"Scoring {opp.get('title', '')[:40]}..."):
                    att_text = opp.get("attachment_text") or ""
                    scored = force_score(opp, attachment_text=att_text)
                    scored["attachment_text"] = att_text or None
                    upsert_opportunity(scored)
                    set_pipeline_status(
                        esid, "expiring_soon",
                        notes=f"Scored from description — {scored.get('fit_score', 0)}/100",
                    )
                new_score = scored.get("fit_score", 0)
                s2_result = scored.get("stage2") or {}
                st.success(f"Score: **{new_score}/100** — {s2_result.get('recommended_action', 'N/A')}")
                if s2_result.get("summary"):
                    st.info(s2_result["summary"])

        # Pursue / Skip actions — always available
        ec1, ec2 = st.columns(2)
        with ec1:
            with st.popover("Pursue →", use_container_width=True):
                exp_pursue_reason = st.text_input(
                    "Why are we pursuing this?",
                    key=f"exp_pursue_reason_{esid}",
                    placeholder="Deadline approaching but strong fit — fast turnaround",
                )
                if st.button("Confirm Pursue", key=f"exp_confirm_pursue_{esid}", use_container_width=True):
                    _pursue_opportunity(opp, reason=exp_pursue_reason or "Deadline approaching — fast turnaround")
                    st.rerun()
        with ec2:
            with st.popover("Skip →", use_container_width=True):
                exp_skip_reason = st.text_input(
                    "Reason for skipping?",
                    key=f"exp_skip_reason_{esid}",
                    placeholder="Won't make the deadline, not worth rushing",
                )
                if st.button("Confirm Skip", key=f"exp_confirm_skip_{esid}", use_container_width=True):
                    from oppos.outputs.slack_alerts import send_abandon_alert
                    set_pipeline_status(esid, "skipped", notes=exp_skip_reason or "Skipped — deadline too close")
                    send_abandon_alert(opp, reason=exp_skip_reason or "Skipped — deadline too close", label="Skipped")
                    st.rerun()
        st.markdown("---")

# --- In Progress tab ---
with tab_in_progress:
    ip_rows = get_by_pipeline_status("in_progress")
    st.markdown(f'<div style="color: var(--text-tertiary); font-size: 14px; margin-bottom: 16px;"><strong>{len(ip_rows)}</strong> in progress</div>', unsafe_allow_html=True)

    if not ip_rows:
        render_empty("No RFPs in progress yet. Move opportunities here from the Pipeline tab.")
    for opp in ip_rows:
        render_card(opp, "ip")
        ip_sid = opp.get("source_id", "")

        ip_c1, ip_c2, ip_c3 = st.columns([1, 1, 1])

        # Push to Notion
        with ip_c1:
            notion_page_id = opp.get("notion_page_id") or ""
            if notion_page_id:
                st.markdown(
                    f'<a href="https://notion.so/{notion_page_id.replace("-", "")}" target="_blank" '
                    f'style="color: var(--accent-gold); font-size: 13px;">📝 Open in Notion</a>',
                    unsafe_allow_html=True,
                )
                if st.button("🔄 Re-push to Notion", key=f"repush_notion_{ip_sid}", use_container_width=True):
                    _push_to_notion(opp)
            else:
                if st.button("📝 Push to Notion", key=f"push_notion_{ip_sid}", use_container_width=True):
                    _push_to_notion(opp)

        # SDR message for Salesforce opp creation
        with ip_c2:
            from oppos.outputs.slack_alerts import build_sdr_message
            with st.popover("📋 Salesforce Opp", use_container_width=True):
                sdr_msg = build_sdr_message(opp)
                st.code(sdr_msg, language=None)
                st.markdown(
                    '<div style="font-size: 11px; color: var(--text-tertiary);">'
                    'Copy the message above and paste it to the SDRs for Salesforce opp creation. '
                    'Also sent to Slack when you clicked Pursue.</div>',
                    unsafe_allow_html=True,
                )

        # Abandon button
        with ip_c3:
            with st.popover("Abandon", use_container_width=True):
                abandon_reason = st.text_input(
                    "Why are we abandoning this?",
                    key=f"abandon_reason_{ip_sid}",
                    placeholder="Timeline too tight, requirements changed, lost to competitor",
                )
                if st.button("Confirm Abandon", key=f"confirm_abandon_{ip_sid}", type="primary", use_container_width=True):
                    from oppos.outputs.slack_alerts import send_abandon_alert
                    set_pipeline_status(ip_sid, "lost", notes=abandon_reason or "Abandoned after pursuit")
                    send_abandon_alert(opp, reason=abandon_reason or "")
                    st.rerun()
        st.markdown("---")

# --- Submitted tab ---
with tab_submitted:
    sub_rows = get_by_pipeline_status("submitted")
    st.markdown(f'<div style="color: var(--text-tertiary); font-size: 14px; margin-bottom: 16px;"><strong>{len(sub_rows)}</strong> submitted</div>', unsafe_allow_html=True)

    if not sub_rows:
        render_empty("No submissions yet. Mark RFPs as submitted once you've responded.")
    for opp in sub_rows:
        render_card(opp, "sub")

# --- Archive tab (won, lost, skipped) ---
with tab_archive:
    won_rows = get_by_pipeline_status("won")
    lost_rows = get_by_pipeline_status("lost")
    skipped_rows = get_by_pipeline_status("skipped")
    archive_rows = won_rows + lost_rows + skipped_rows
    st.markdown(f'<div style="color: var(--text-tertiary); font-size: 14px; margin-bottom: 16px;"><strong>{len(won_rows)}</strong> won &middot; <strong>{len(lost_rows)}</strong> lost &middot; <strong>{len(skipped_rows)}</strong> skipped</div>', unsafe_allow_html=True)

    if not archive_rows:
        render_empty("No archived opportunities yet.")
    for opp in archive_rows:
        render_card(opp, "arch")

# --- Expired tab ---
with tab_expired:
    expired_rows = get_by_pipeline_status("expired")
    expired_rows.sort(key=lambda r: r.get("response_deadline") or "", reverse=True)
    st.markdown(
        f'<div style="color: var(--accent-red); font-size: 14px; margin-bottom: 16px;">'
        f'<strong>{len(expired_rows)}</strong> expired — deadline passed before action was taken</div>',
        unsafe_allow_html=True,
    )

    if not expired_rows:
        render_empty("No expired opportunities. Deadlines are checked automatically on each page load.")
    for opp in expired_rows:
        render_card(opp, "expd", show_status_controls=False)

st.markdown(f"""
<div class="oppos-footer">
    <span style="color: var(--text-secondary);">{NUTRIENT_DOTS_SVG}</span>
    <span>OppOS &middot; Automated RFP Intelligence</span>
</div>
""", unsafe_allow_html=True)
