#!/usr/bin/env python3
"""Seed the local demo database with realistic sample data (no API calls).

Creates data/local-demo.db with a few scored opportunities across LOBs, a portal
registration, and one active pursuit with a partially completed checklist — enough
to demo or test the Pursuits workspace without touching the shared Turso DB.

Usage:
    python scripts/seed_local_demo.py          # then: preview "oppos-dashboard-local" (port 8502)
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

os.environ.setdefault("OPPOS_ENV_FILE", ".env.local")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import oppos.config as cfg  # noqa: E402  (loads .env.local)
from oppos.storage import db  # noqa: E402


def _opp(sid: str, **kw) -> dict:
    base = {
        "source_id": sid, "source": "rhode_island_osp", "notice_type": "RFP", "naics_code": "541512",
        "posted_date": date.today().isoformat(), "set_aside": "", "classification_code": "", "office": "",
        "point_of_contact": {"name": "Pat Buyer", "email": "pat.buyer@example.gov", "phone": ""},
        "resource_links": [], "raw": {}, "recommended_action": "investigate", "stage1": {"relevant": True, "confidence": 0.9, "lobs": []},
    }
    base.update(kw)
    return base


def main() -> None:
    assert not db._use_turso(), "Refusing to seed: Turso is configured. Run with OPPOS_ENV_FILE=.env.local"
    print(f"Seeding {cfg.DB_PATH}")
    db.init_db()
    for table in ("opportunities", "pursuits", "pursuit_events", "reminders_sent", "source_health",
                  "portal_registrations", "meta"):
        db._execute(f"DELETE FROM {table}")  # demo state must be reproducible

    due_soon = (date.today() + timedelta(days=5)).isoformat()
    due_later = (date.today() + timedelta(days=24)).isoformat()

    wf = _opp(
        "demo-wf-1", title="Workforce Development Case Management System", agency="Rhode Island Dept. of Labor and Training",
        response_deadline=due_later, url="https://ridop.ri.gov/rivip/example-1", place_of_performance="Rhode Island",
        description="The Department seeks a configurable case management platform to replace paper-based intake, "
                    "eligibility review, and appeals tracking for workforce programs. Must support online forms, "
                    "document upload, role-based routing, audit trails, and reporting. SOC 2 Type II required.",
        lob="workflow", fit_score=81, recommended_action="pursue",
        stage2={"fit_score": 81, "fit_tier": 1, "lob": "workflow", "industry": "Government / Workforce",
                "pattern_match": "case_management", "similar_win": "Tennessee DOHR — FMLA case management",
                "deployment_recommendation": "enhanced_cloud", "profile_depth": "full",
                "strengths": [{"claim": "Native intake → review → appeals case lifecycle", "evidence": "replace paper-based intake, eligibility review, and appeals tracking"},
                              {"claim": "Role-based routing and audit trails are core platform features", "evidence": "role-based routing, audit trails, and reporting"}],
                "risks": [{"claim": "SOC 2 Type II evidence must be packaged for submission", "evidence": "SOC 2 Type II required"}],
                "knowledge_gaps": ["User counts and concurrent caseload not stated", "Incumbent system not named"],
                "competitive_notes": "Likely Salesforce SI shops and Tyler; displacement of a paper process, not a product.",
                "recommended_action": "pursue", "summary": "Strong case-management pattern match in a proven vertical."},
    )
    sdk = _opp(
        "demo-sdk-1", title="Web-Based Plan Review Portal — PDF Viewing and Markup Component", agency="City of Providence — Inspections",
        response_deadline=due_soon, url="https://ridop.ri.gov/rivip/example-2", place_of_performance="Rhode Island",
        description="The City is procuring a plan review portal. The selected integrator must provide in-browser "
                    "viewing, measurement, and markup of large-format PDF drawings, with redaction of applicant PII "
                    "and offline access for field inspectors on iOS tablets.",
        lob="sdk", fit_score=57, recommended_action="investigate",
        stage2={"fit_score": 57, "fit_tier": 3, "lob": "sdk", "industry": "Government / Permitting", "play": "partner_si",
                "platforms": ["web", "ios"], "profile_depth": "thin", "component_only": True,
                "strengths": [{"claim": "In-browser viewing and markup of large PDFs is core Web SDK capability", "evidence": "in-browser viewing, measurement, and markup of large-format PDF drawings"},
                              {"claim": "Redaction and iOS offline viewing map to SDK features", "evidence": "redaction of applicant PII and offline access for field inspectors on iOS tablets"}],
                "risks": [{"claim": "Nutrient would be a component for the integrator, not the prime", "evidence": "The selected integrator must provide"}],
                "knowledge_gaps": ["Which integrators are bidding", "Document volume and page sizes"],
                "competitive_notes": "Apryse / Bluebeam-style tooling embedded by the SI.",
                "recommended_action": "investigate", "summary": "Thin SDK profile — likely partner/SI play; route to SDK sales."},
    )
    lc = _opp(
        "demo-lc-1", title="SharePoint Records Digitization and OCR", agency="Rhode Island Secretary of State — Archives",
        response_deadline=due_later, url="https://ridop.ri.gov/rivip/example-3", place_of_performance="Rhode Island",
        description="Convert 1.2 million scanned pages stored in SharePoint Online to searchable PDF/A, with automated "
                    "metadata tagging and Power Automate-driven retention workflows.",
        lob="low_code", fit_score=55, recommended_action="investigate",
        stage2={"fit_score": 55, "fit_tier": 3, "lob": "low_code", "industry": "Government / Records", "platform_context": "sharepoint",
                "profile_depth": "thin",
                "strengths": [{"claim": "Bulk OCR to PDF/A inside SharePoint Online is the Document Searchability use case", "evidence": "scanned pages stored in SharePoint Online to searchable PDF/A"},
                              {"claim": "Power Automate retention flows fit Document Converter actions", "evidence": "Power Automate-driven retention workflows"}],
                "risks": [{"claim": "Volume pricing and throughput must be confirmed", "evidence": "1.2 million scanned pages"}],
                "knowledge_gaps": ["Timeline for conversion", "Existing OCR vendor"],
                "competitive_notes": "ABBYY, Adlib.", "recommended_action": "investigate",
                "summary": "Thin Low-Code profile — strong SharePoint/OCR signals; verify with Catalyst."},
    )
    for o in (wf, sdk, lc):
        db.upsert_opportunity(o)
    db.set_pipeline_status("demo-wf-1", "in_progress", notes="Strong fit — pursuing", assigned_to="Demo SDR")
    db.set_pipeline_status("demo-sdk-1", "expiring_soon", notes="Deadline within 7 days")
    db.set_pipeline_status("demo-lc-1", "qualified", notes="Scored from attachments — 55/100")

    db.upsert_portal_registration("rhode_island_osp", display_name="Ocean State Procures (RI)", status="not_registered",
                                  lead_time_days=10, url="https://ridop.ri.gov/rivip", login_owner="",
                                  notes="Requires W-9 and RI business registration before first bid.")

    db.create_pursuit(
        "demo-wf-1", owner_email="demo.sdr@nutrient.io", owner_name="Demo SDR", lob="workflow", reason="Strong fit — pursuing",
        status="active", submission_deadline=due_later, qa_deadline=(date.today() + timedelta(days=9)).isoformat(),
        submission_method="portal", portal="rhode_island_osp", registration_status="not_registered",
        checklist_json=json.dumps({"go_no_go": True, "salesforce": True}), next_action="Confirm vendor registration with ops",
        created_by="demo.sdr@nutrient.io",
    )
    db.add_pursuit_event("demo-wf-1", "demo.sdr@nutrient.io", "started", "Strong fit — pursuing")
    db.add_pursuit_event("demo-wf-1", "demo.sdr@nutrient.io", "updated", "checklist updated, next_action=Confirm vendor registration with ops")
    db.record_source_health("rhode_island_osp", "Ocean State Procures (RI)", ok=True, count=22, new=3, duration_s=4.2)
    db.record_source_health("kentucky_emars", "eMARS Kentucky (KY)", ok=False, count=0, new=0,
                            error="PlaywrightNotInstalled: cannot render CGI Advantage SPA", duration_s=0.3)
    db.set_meta("last_scan", __import__("datetime").datetime.utcnow().isoformat())
    db.set_excluded_sources([])  # demo starts with no exclusions
    print("Seeded 3 opportunities, 1 registration, 1 active pursuit, 2 source-health rows.")


if __name__ == "__main__":
    main()
