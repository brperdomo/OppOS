"""Sync scored opportunities to a Notion database."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from notion_client import Client

from oppos.config import NOTION_DATABASE_ID, NOTION_TOKEN

logger = logging.getLogger(__name__)

_client: Client | None = None


def _get_client() -> Client:
    global _client
    if _client is None:
        if not NOTION_TOKEN:
            raise RuntimeError("NOTION_TOKEN not set")
        _client = Client(auth=NOTION_TOKEN)
    return _client


def _truncate(text: str, max_len: int = 2000) -> str:
    return text[:max_len] if text else ""


def _upload_file_to_notion(client: Client, page_id: str, filepath: Path) -> bool:
    """Upload a file to a Notion page using the file uploads API."""
    try:
        upload = client.file_uploads.create(
            parent={"type": "page", "page_id": page_id},
            name=filepath.name,
        )
        upload_id = upload["id"]

        with open(filepath, "rb") as f:
            client.file_uploads.send(
                upload_id,
                file=f,
                filename=filepath.name,
            )

        client.file_uploads.complete(upload_id)

        client.blocks.children.append(
            block_id=page_id,
            children=[{
                "object": "block",
                "type": "file",
                "file": {
                    "type": "file_upload",
                    "file_upload": {"id": upload_id},
                },
            }],
        )
        logger.info("Uploaded attachment: %s", filepath.name)
        return True
    except Exception as e:
        logger.warning("Failed to upload %s to Notion: %s", filepath.name, e)
        return False


def push_opportunity(opp: dict[str, Any], attachment_paths: list[Path] | None = None) -> str | None:
    """Create or update a page in the Notion RFP database. Returns the page ID."""
    if not NOTION_DATABASE_ID:
        logger.warning("NOTION_DATABASE_ID not set — skipping Notion sync")
        return None

    client = _get_client()
    s2 = opp.get("stage2") or {}
    if isinstance(s2, str):
        try:
            s2 = json.loads(s2)
        except json.JSONDecodeError:
            s2 = {}

    score = opp.get("fit_score", 0)
    action = s2.get("recommended_action", opp.get("recommended_action", "pending"))

    action_color_map = {
        "pursue": "green",
        "investigate": "yellow",
        "monitor": "orange",
        "skip": "red",
    }

    properties = {
        "Name": {"title": [{"text": {"content": _truncate(opp.get("title", "Untitled"), 200)}}]},
        "Fit Score": {"number": score},
        "Action": {"select": {"name": action.capitalize(), "color": action_color_map.get(action, "default")}},
        "Agency": {"rich_text": [{"text": {"content": _truncate(opp.get("agency", ""), 200)}}]},
        "Deadline": {},
        "Source": {"select": {"name": opp.get("source", "sam_gov")}},
        "Pattern": {"select": {"name": s2.get("pattern_match", "other")}},
        "Industry": {"rich_text": [{"text": {"content": _truncate(s2.get("industry", ""), 100)}}]},
        "Similar Win": {"rich_text": [{"text": {"content": _truncate(s2.get("similar_win") or "", 200)}}]},
        "Solicitation #": {"rich_text": [{"text": {"content": _truncate(opp.get("solicitation_number", ""), 100)}}]},
        "URL": {"url": opp.get("url") or None},
    }

    deadline = opp.get("response_deadline")
    if deadline:
        properties["Deadline"] = {"date": {"start": deadline[:10]}}
    else:
        del properties["Deadline"]

    children = []

    summary = s2.get("summary", "")
    if summary:
        children.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {"rich_text": [{"text": {"content": "AI Assessment"}}]},
        })
        children.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": [{"text": {"content": _truncate(summary, 2000)}}]},
        })

    strengths = s2.get("strengths", [])
    if strengths:
        children.append({
            "object": "block",
            "type": "heading_3",
            "heading_3": {"rich_text": [{"text": {"content": "Strengths"}}]},
        })
        for s in strengths[:8]:
            children.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": [{"text": {"content": _truncate(s, 500)}}]},
            })

    risks = s2.get("risks", [])
    if risks:
        children.append({
            "object": "block",
            "type": "heading_3",
            "heading_3": {"rich_text": [{"text": {"content": "Risks"}}]},
        })
        for r in risks[:5]:
            children.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": [{"text": {"content": _truncate(r, 500)}}]},
            })

    deployment = s2.get("deployment_recommendation", "")
    competitive = s2.get("competitive_notes", "")
    if deployment or competitive:
        children.append({
            "object": "block",
            "type": "heading_3",
            "heading_3": {"rich_text": [{"text": {"content": "Notes"}}]},
        })
        if deployment:
            children.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [{"text": {"content": f"Deployment: {deployment}"}}]},
            })
        if competitive:
            children.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [{"text": {"content": f"Competitive: {_truncate(competitive, 1000)}"}}]},
            })

    if attachment_paths:
        children.append({
            "object": "block",
            "type": "heading_3",
            "heading_3": {"rich_text": [{"text": {"content": "Attachments"}}]},
        })

    try:
        page = client.pages.create(
            parent={"database_id": NOTION_DATABASE_ID},
            properties=properties,
            children=children[:100],
        )
        page_id = page["id"]
        logger.info("Notion page created for '%s': %s", opp.get("title", "?"), page_id)

        if attachment_paths:
            for filepath in attachment_paths:
                _upload_file_to_notion(client, page_id, filepath)

        return page_id
    except Exception as e:
        logger.error("Notion sync failed for '%s': %s", opp.get("title", "?"), e)
        return None
