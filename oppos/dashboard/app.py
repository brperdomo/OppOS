"""OppOS Streamlit dashboard.

Run with:
    streamlit run oppos/dashboard/app.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import os
try:
    for key in ("TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN", "SAM_GOV_API_KEY", "ANTHROPIC_API_KEY", "SLACK_WEBHOOK_URL"):
        if key not in os.environ and key in st.secrets:
            os.environ[key] = st.secrets[key]
except Exception:
    pass

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

st.set_page_config(page_title="OppOS", page_icon="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'><text y='14' font-size='14'>O</text></svg>", layout="wide")

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
    gap: 16px;
    padding: 24px 0;
    margin-bottom: 8px;
}
.oppos-header h1 {
    font-family: 'Inter', sans-serif;
    font-size: 28px;
    font-weight: 700;
    color: var(--text-primary);
    margin: 0;
    letter-spacing: -0.5px;
}
.oppos-header .subtitle {
    font-size: 14px;
    color: var(--text-tertiary);
    font-weight: 400;
}
.oppos-logo {
    width: 36px;
    height: 36px;
    background: var(--accent-gold);
    border-radius: var(--radius-sm);
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 700;
    font-size: 18px;
    color: var(--bg-primary);
}

/* Stats bar */
.stats-bar {
    display: flex;
    gap: 24px;
    padding: 16px 24px;
    background: var(--bg-secondary);
    border-radius: var(--radius-md);
    border: 1px solid var(--border-subtle);
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
.score-pursue .score-number { color: var(--accent-green); }
.score-investigate .score-number { color: var(--accent-gold); }
.score-monitor .score-number { color: var(--accent-orange); }
.score-skip .score-number { color: var(--text-tertiary); }

/* Action badge */
.action-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 12px;
    border-radius: 100px;
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.action-pursue {
    background: rgba(110, 180, 121, 0.15);
    color: var(--accent-green);
    border: 1px solid rgba(110, 180, 121, 0.3);
}
.action-investigate {
    background: rgba(240, 201, 102, 0.15);
    color: var(--accent-gold);
    border: 1px solid rgba(240, 201, 102, 0.3);
}
.action-monitor {
    background: rgba(232, 148, 76, 0.15);
    color: var(--accent-orange);
    border: 1px solid rgba(232, 148, 76, 0.3);
}
.action-skip {
    background: rgba(137, 126, 112, 0.15);
    color: var(--text-tertiary);
    border: 1px solid rgba(137, 126, 112, 0.3);
}

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

st.markdown("""
<div class="oppos-header">
    <div class="oppos-logo">O</div>
    <div>
        <h1>OppOS</h1>
        <div class="subtitle">RFP Opportunity Pipeline</div>
    </div>
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

all_rows = get_all_scored(min_score=0)

status_counts = {}
for s in PIPELINE_LABELS:
    status_counts[s] = sum(1 for r in all_rows if (r.get("pipeline_status") or "new") == s)

pursue_count = sum(1 for r in all_rows if r.get("recommended_action") == "pursue")
investigate_count = sum(1 for r in all_rows if r.get("recommended_action") == "investigate")

st.markdown(f"""
<div class="stats-bar">
    <div class="stat-item">
        <div class="stat-value">{len(all_rows)}</div>
        <div class="stat-label">Total Scored</div>
    </div>
    <div class="stat-item">
        <div class="stat-value green">{pursue_count}</div>
        <div class="stat-label">Pursue</div>
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


def _score_class(action: str) -> str:
    return f"score-{action}"


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def render_card(opp: dict, tab_key: str, show_status_controls: bool = True) -> None:
    s2_raw = opp.get("stage2_json")
    s2 = {}
    if s2_raw:
        try:
            s2 = json.loads(s2_raw) if isinstance(s2_raw, str) else s2_raw
        except (json.JSONDecodeError, TypeError):
            pass

    sid = opp.get("source_id", "")
    score = opp.get("fit_score", 0)
    action = opp.get("recommended_action", "pending")
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

    status_label = PIPELINE_LABELS.get(pipeline_status, pipeline_status)

    st.markdown(f"""
    <div class="opp-card">
        <div class="opp-card-header">
            <div style="flex: 1;">
                {title_html}
                <div style="font-size: 14px; color: var(--text-secondary); margin-top: 4px;">
                    <span style="color: var(--accent-gold); font-weight: 600;">{state_name}</span>
                    <span style="color: var(--text-tertiary); margin: 0 6px;">&middot;</span>
                    {agency}
                </div>
                <div class="opp-meta">
                    <span class="pipeline-badge pipeline-{pipeline_status}">{status_label}</span>
                    <span class="action-badge action-{action}">{action}</span>
                    <span class="opp-tag source">{source_label}</span>
                    {f'<span class="opp-tag">{sol_num}</span>' if sol_num else ''}
                    <span class="opp-tag deadline">{deadline_display}</span>
                </div>
            </div>
            <div class="score-badge {_score_class(action)}">
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
    col_f1, col_f2, col_f3, col_f4 = st.columns(4)
    with col_f1:
        min_score = st.slider("Min Score", 0, 100, 40, step=5, key="pipe_score")
    with col_f2:
        action_filter = st.multiselect(
            "Action",
            ["pursue", "investigate", "monitor", "skip"],
            default=["pursue", "investigate"],
            key="pipe_action",
        )
    with col_f3:
        sort_by = st.selectbox("Sort by", ["Fit Score", "Deadline", "Posted"], key="pipe_sort")
    with col_f4:
        source_filter = st.multiselect(
            "Source",
            list(SOURCE_LABELS.keys()),
            format_func=lambda k: SOURCE_LABELS.get(k, k),
            key="pipe_source",
        )

    rows = get_all_scored(min_score=min_score)
    rows = [r for r in rows if (r.get("pipeline_status") or "new") == "new"]

    if action_filter:
        rows = [r for r in rows if r.get("recommended_action") in action_filter]
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
