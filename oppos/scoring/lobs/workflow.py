"""Nutrient Workflow Automation — full positioning profile (vetted)."""

from oppos.scoring.capability_profile import CAPABILITY_PROFILE
from oppos.scoring.lobs.base import LOB

WORKFLOW = LOB(
    key="workflow",
    label="Workflow",
    router_blurb=(
        "Nutrient Workflow Automation (fka Integrify): no/low-code process automation and case "
        "management platform — intake forms, approval routing, task management, SLA tracking, "
        "document generation and e-signature, audit trails, dashboards. Buyers: state/local "
        "government, higher ed, healthcare, and financial-services operations teams replacing "
        "paper/email processes (HR, finance approvals, permits/licensing, grants, case management, "
        "IT requests)."
    ),
    profile=CAPABILITY_PROFILE,
    depth="full",
    extras_schema=(
        '"pattern_match": "<closest pattern: case_management | hr_compliance | guided_decision_support | financial_approvals | it_request_management | ap_invoice | other>",',
        '"similar_win": "<closest past win or customer example, or null>",',
        '"deployment_recommendation": "<standard_cloud | enhanced_cloud | self_managed | private_cluster | tbs_hosting>",',
    ),
    extras_defaults={"pattern_match": "other", "similar_win": None, "deployment_recommendation": ""},
)
