"""Backward-compatible shim — the Workflow profile now lives in
oppos/scoring/lobs/profiles/workflow.md and is loaded by oppos.scoring.lobs.workflow."""

from oppos.scoring.lobs.workflow import CAPABILITY_PROFILE  # noqa: F401

__all__ = ["CAPABILITY_PROFILE"]
