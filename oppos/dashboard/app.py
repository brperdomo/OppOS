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

for key in ("TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN", "SAM_GOV_API_KEY", "ANTHROPIC_API_KEY", "SLACK_WEBHOOK_URL", "NUTRIENT_API_KEY"):
    try:
        if hasattr(st, "secrets") and key in st.secrets:
            val = str(st.secrets[key]).strip().strip('"').strip("'")
            if val:
                os.environ[key] = val
                _secrets_loaded.append(key)
    except Exception as e:
        _secrets_errors.append(f"{key}: {e}")

from oppos.config import DB_PATH
from oppos.sources.registry import list_available
from oppos.storage.db import get_all_scored, get_by_pipeline_status, init_db, set_pipeline_status

ATTACHMENTS_DIR = DB_PATH.parent / "attachments"

SOURCE_STATE_MAP = {
    "sam_gov": "Federal",
    "nevada_epro": "Nevada",
    "massachusetts_commbuys": "Massachusetts",
    "new_jersey_njstart": "New Jersey",
    "illinois_bidbuy": "Illinois",
    "oregon_oregonbuys": "Oregon",
    "arkansas_arbuy": "Arkansas",
    "arizona_app": "Arizona",
    "iowa_impacs": "Iowa",
    "montana_emacs": "Montana",
    "new_mexico_epro": "New Mexico",
    "pennsylvania_costars": "Pennsylvania",
    "utah_dps": "Utah",
    "west_virginia_wvpurchasing": "West Virginia",
    "kentucky_emars": "Kentucky",
    "colorado_vss": "Colorado",
    "michigan_sigma": "Michigan",
    "alaska_iris": "Alaska",
    "maine_vss": "Maine",
    "tennessee_edison": "Tennessee",
    "georgia_tgm": "Georgia",
    "indiana_idoa": "Indiana",
    "kansas_esupplier": "Kansas",
    "minnesota_swift": "Minnesota",
    "oklahoma_omes": "Oklahoma",
    "wisconsin_vendornet": "Wisconsin",
    "maryland_emma": "Maryland",
    "virginia_eva": "Virginia",
    "north_dakota_cps": "North Dakota",
    "vermont_bgs": "Vermont",
    "florida_mfmp": "Florida",
    "north_carolina_ips": "North Carolina",
    "mississippi_magic": "Mississippi",
    "south_carolina_sceis": "South Carolina",
}

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
    border-radius: var(--radius-md);
    padding: 24px;
    margin-bottom: 16px;
    transition: border-color 0.2s ease;
}
.opp-card:hover {
    border-color: var(--border-medium);
}
.opp-card-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 16px;
    margin-bottom: 16px;
}
.opp-title {
    font-size: 18px;
    font-weight: 600;
    color: var(--text-primary);
    text-decoration: none;
    line-height: 1.3;
}
.opp-title:hover {
    color: var(--accent-gold);
}
a.opp-title { color: var(--text-primary); text-decoration: none; }
a.opp-title:hover { color: var(--accent-gold); }

.opp-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 8px;
}
.opp-tag {
    display: inline-flex;
    align-items: center;
    padding: 3px 10px;
    border-radius: 100px;
    font-size: 12px;
    font-weight: 500;
    border: 1px solid var(--border-subtle);
    color: var(--text-secondary);
    background: transparent;
}
.opp-tag.source {
    border-color: rgba(222, 157, 204, 0.3);
    color: var(--accent-pink);
}
.opp-tag.deadline {
    border-color: rgba(240, 201, 102, 0.3);
    color: var(--accent-gold);
}

/* Score badge */
.score-badge {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-width: 72px;
    height: 72px;
    border-radius: var(--radius-md);
    background: var(--bg-tertiary);
    border: 1px solid var(--border-subtle);
    flex-shrink: 0;
}
.score-number {
    font-size: 28px;
    font-weight: 700;
    line-height: 1;
}
.score-label {
    font-size: 10px;
    font-weight: 500;
    color: var(--text-tertiary);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-top: 2px;
}
.score-high .score-number { color: var(--accent-green); }
.score-mid .score-number { color: var(--accent-gold); }
.score-low .score-number { color: var(--text-tertiary); }

/* Detail grid */
.detail-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 12px;
    margin-top: 16px;
    padding-top: 16px;
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
SOURCE_LABELS = dict(list_available())

PIPELINE_LABELS = {
    "new": "New",
    "in_progress": "In Progress",
    "submitted": "Submitted",
    "won": "Won",
    "lost": "Lost",
    "skipped": "Skipped",
}

STATUS_OPTIONS = list(PIPELINE_LABELS.keys())
STATUS_DISPLAY = list(PIPELINE_LABELS.values())


def _run_scan() -> dict:
    """Run the pipeline in-process and return stats."""
    import logging
    from oppos.config import STAGE2_MIN_SCORE
    from oppos.scoring.qualifier import qualify
    from oppos.sources.registry import get_enabled_sources
    from oppos.storage.db import is_seen, upsert_opportunity

    logging.basicConfig(level=logging.INFO)
    sources = get_enabled_sources()
    stats = {"fetched": 0, "new": 0, "scored": 0, "errors": []}
    posted_from = datetime.now() - timedelta(days=14)

    for key, name, fetch_fn in sources:
        try:
            opps = fetch_fn(posted_from=posted_from) if key == "sam_gov" else fetch_fn()
            stats["fetched"] += len(opps)
            for opp in opps:
                if is_seen(opp["source_id"]):
                    continue
                stats["new"] += 1
                scored = qualify(opp)
                if scored.get("fit_score", 0) >= STAGE2_MIN_SCORE:
                    stats["scored"] += 1
                upsert_opportunity(scored)
        except Exception as e:
            stats["errors"].append(f"{name}: {e}")

    return stats


# --- Scan button row ---
scan_col, spacer_col = st.columns([1, 3])
with scan_col:
    scan_clicked = st.button("Scan for New RFPs", use_container_width=True, type="primary")

if scan_clicked:
    with st.spinner("Scanning all sources for new opportunities..."):
        scan_stats = _run_scan()
    if scan_stats["new"] > 0:
        st.markdown(f"""
        <div class="scan-result">
            Found <strong>{scan_stats["new"]} new</strong> opportunities
            ({scan_stats["scored"]} scored above threshold)
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

tab_pipeline, tab_in_progress, tab_submitted, tab_archive = st.tabs([
    f"Pipeline ({status_counts.get('new', 0)})",
    f"In Progress ({status_counts.get('in_progress', 0)})",
    f"Submitted ({status_counts.get('submitted', 0)})",
    f"Archive ({status_counts.get('won', 0) + status_counts.get('lost', 0) + status_counts.get('skipped', 0)})",
])


def _score_class(score: int) -> str:
    if score >= 65:
        return "score-high"
    if score >= 40:
        return "score-mid"
    return "score-low"


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _run_deep_scan(opp: dict, tab_key: str) -> None:
    """Download attachments, OCR via Nutrient, re-score with full text."""
    from oppos.scoring.qualifier import qualify
    from oppos.sources.attachments import download_attachments
    from oppos.sources.extract_text import extract_text_from_attachments
    from oppos.storage.db import upsert_opportunity

    sid = opp.get("source_id", "")
    title = opp.get("title", "Untitled")

    existing_text = opp.get("attachment_text") or ""
    if existing_text:
        st.info("Using previously extracted text (no credits used).")
        with st.spinner("Re-scoring with cached attachment content..."):
            scored = qualify(opp, attachment_text=existing_text)
            scored["attachment_text"] = existing_text
            upsert_opportunity(scored)

        new_score = scored.get("fit_score", 0)
        old_score = int(opp.get("fit_score") or 0)
        delta = new_score - old_score
        delta_str = f"+{delta}" if delta > 0 else str(delta)
        st.success(
            f"Re-scored with cached OCR ({len(existing_text):,} chars). "
            f"Score: {old_score} → **{new_score}** ({delta_str})"
        )
        st.rerun()
        return

    with st.spinner(f"Downloading attachments for {title[:50]}..."):
        att_files = download_attachments(opp)

    if not att_files:
        st.warning("No attachments found for this RFP.")
        return

    pdf_count = sum(1 for f in att_files if f.suffix.lower() == ".pdf")
    if pdf_count == 0:
        st.warning("No PDF attachments to scan.")
        return

    with st.spinner(f"Extracting text from {pdf_count} PDF(s) via Nutrient OCR..."):
        attachment_text = extract_text_from_attachments(att_files)

    if not attachment_text:
        st.warning("Could not extract text from attachments.")
        return

    with st.spinner("Re-scoring with full attachment content..."):
        scored = qualify(opp, attachment_text=attachment_text)
        scored["attachment_text"] = attachment_text
        upsert_opportunity(scored)

    new_score = scored.get("fit_score", 0)
    old_score = int(opp.get("fit_score") or 0)
    delta = new_score - old_score
    delta_str = f"+{delta}" if delta > 0 else str(delta)

    st.success(
        f"Deep scan complete — extracted {len(attachment_text):,} chars from {pdf_count} PDF(s). "
        f"Score: {old_score} → **{new_score}** ({delta_str})"
    )
    st.rerun()


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

    st.markdown(f"""
    <div class="opp-card">
        <div class="opp-card-header">
            <div style="flex: 1;">
                {new_badge_html} {title_html}
                <div style="font-size: 14px; color: var(--text-secondary); margin-top: 4px;">
                    <span style="color: var(--accent-gold); font-weight: 600;">{state_name}</span>
                    <span style="color: var(--text-tertiary); margin: 0 6px;">&middot;</span>
                    {agency}
                </div>
                <div class="opp-meta">
                    <span class="pipeline-badge pipeline-{pipeline_status}">{status_label}</span>
                    <span class="opp-tag source">{source_label}</span>
                    {f'<span class="opp-tag">{sol_num}</span>' if sol_num else ''}
                    <span class="opp-tag deadline">{deadline_display}</span>
                </div>
            </div>
            <div class="score-badge {_score_class(score)}">
                <div class="score-number">{score}</div>
                <div class="score-label">Score</div>
            </div>
        </div>
        <div class="detail-grid">
            <div class="detail-item">
                <div class="detail-label">Pattern</div>
                <div class="detail-value">{_esc(s2.get('pattern_match', '—'))}</div>
            </div>
            <div class="detail-item">
                <div class="detail-label">Industry</div>
                <div class="detail-value">{_esc(s2.get('industry', '—'))}</div>
            </div>
            <div class="detail-item">
                <div class="detail-label">Notice Type</div>
                <div class="detail-value">{_esc(opp.get('notice_type', '') or '—')}</div>
            </div>
            <div class="detail-item">
                <div class="detail-label">Similar Win</div>
                <div class="detail-value">{_esc(s2.get('similar_win', '') or '—')}</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

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
                    set_pipeline_status(sid, new_status, notes=new_notes)
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

    with st.expander("AI Assessment"):
        summary = s2.get("summary", "")
        if summary:
            st.markdown(f'<div class="assessment-summary">{_esc(summary)}</div>', unsafe_allow_html=True)

        col_s, col_r = st.columns(2)
        with col_s:
            strengths = s2.get("strengths", [])
            if strengths:
                st.markdown('<div class="detail-label" style="margin-bottom:8px;">Strengths</div>', unsafe_allow_html=True)
                for s in strengths:
                    st.markdown(f'<div class="strength-item">+ {_esc(s)}</div>', unsafe_allow_html=True)
        with col_r:
            risks = s2.get("risks", [])
            if risks:
                st.markdown('<div class="detail-label" style="margin-bottom:8px;">Risks</div>', unsafe_allow_html=True)
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

    # --- Deep Scan button ---
    has_cached_ocr = bool(opp.get("attachment_text"))
    ds_col1, ds_col2 = st.columns([1, 3])
    with ds_col1:
        deep_scan = st.button(
            "Re-score (cached)" if has_cached_ocr else "Deep Scan with OCR",
            key=f"deepscan_{tab_key}_{sid}",
            use_container_width=True,
            help="Re-score using previously extracted text (no credits used)" if has_cached_ocr
            else "Download attachments, extract text via Nutrient OCR, and re-score this RFP",
        )
    with ds_col2:
        hint = "OCR text cached — re-score without using Nutrient credits" if has_cached_ocr \
            else "Reads PDF attachments and re-scores with full requirements context"
        st.markdown(
            f'<div style="font-size: 12px; color: var(--text-tertiary); padding-top: 8px;">'
            f'{hint}</div>',
            unsafe_allow_html=True,
        )

    if deep_scan:
        _run_deep_scan(opp, tab_key)

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

# --- In Progress tab ---
with tab_in_progress:
    ip_rows = get_by_pipeline_status("in_progress")
    st.markdown(f'<div style="color: var(--text-tertiary); font-size: 14px; margin-bottom: 16px;"><strong>{len(ip_rows)}</strong> in progress</div>', unsafe_allow_html=True)

    if not ip_rows:
        render_empty("No RFPs in progress yet. Move opportunities here from the Pipeline tab.")
    for opp in ip_rows:
        render_card(opp, "ip")

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

st.markdown(f"""
<div class="oppos-footer">
    <span style="color: var(--text-secondary);">{NUTRIENT_DOTS_SVG}</span>
    <span>OppOS &middot; Automated RFP Intelligence</span>
</div>
""", unsafe_allow_html=True)
