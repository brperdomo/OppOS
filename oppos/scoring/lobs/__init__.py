"""Line-of-business registry for RFP qualification.

Stage 1 routes each RFP to the LOB(s) that could address it; Stage 2 scores
against the primary LOB's positioning profile. Workflow has a vetted profile;
the others are thin descriptions until `/build-lob-profile` generates real ones.
"""

from __future__ import annotations

from oppos.scoring.lobs.base import LOB
from oppos.scoring.lobs.dws import DWS
from oppos.scoring.lobs.low_code import LOW_CODE
from oppos.scoring.lobs.sdk import SDK
from oppos.scoring.lobs.workflow import WORKFLOW

LOBS: dict[str, LOB] = {
    WORKFLOW.key: WORKFLOW,
    LOW_CODE.key: LOW_CODE,
    SDK.key: SDK,
    DWS.key: DWS,
}

DEFAULT_LOB = WORKFLOW.key


def get_lob(key: str | None) -> LOB | None:
    if not key:
        return None
    return LOBS.get(str(key).strip().lower())


def lob_label(key: str | None) -> str:
    lob = get_lob(key)
    return lob.label if lob else (str(key) if key else "")


__all__ = ["LOB", "LOBS", "DEFAULT_LOB", "get_lob", "lob_label"]
