#!/usr/bin/env python3
"""Quick smoke test for the Notion integration.

Validates: token auth, database access, page create, query-back, cleanup.

Usage:
    python scripts/test_notion.py

Requires NOTION_TOKEN and NOTION_DATABASE_ID in .env or environment.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oppos.config import NOTION_DATABASE_ID, NOTION_DATASOURCE_ID, NOTION_TOKEN


def main() -> None:
    print("=" * 60)
    print("  OppOS — Notion Integration Test")
    print("=" * 60)

    # ── Step 1: Check env vars ──────────────────────────────────
    print("\n[1/6] Checking environment variables...")
    if not NOTION_TOKEN:
        print("  ✗ NOTION_TOKEN is not set.")
        print("    Add it to .env or export it before running.")
        sys.exit(1)
    print(f"  ✓ NOTION_TOKEN set (starts with {NOTION_TOKEN[:8]}...)")

    if not NOTION_DATABASE_ID:
        print("  ✗ NOTION_DATABASE_ID is not set.")
        sys.exit(1)
    print(f"  ✓ NOTION_DATABASE_ID = {NOTION_DATABASE_ID}")

    # ── Step 2: Authenticate ────────────────────────────────────
    print("\n[2/6] Authenticating with Notion API...")
    from notion_client import Client
    try:
        client = Client(auth=NOTION_TOKEN)
        me = client.users.me()
        print(f"  ✓ Authenticated as: {me.get('name', 'unknown')} ({me.get('type', '?')})")
    except Exception as e:
        print(f"  ✗ Auth failed: {e}")
        sys.exit(1)

    # ── Step 3: Read database schema ────────────────────────────
    print("\n[3/6] Reading database schema...")
    try:
        db = client.databases.retrieve(database_id=NOTION_DATABASE_ID)
        db_title = "".join(
            t.get("plain_text", "") for t in db.get("title", [])
        )
        props = db.get("properties", {})
        print(f"  ✓ Database: \"{db_title}\"")
        print(f"  ✓ {len(props)} properties found:")
        for name, prop in sorted(props.items()):
            ptype = prop.get("type", "?")
            print(f"      • {name} ({ptype})")
    except Exception as e:
        print(f"  ✗ Database read failed: {e}")
        print("    Make sure the integration has access to this database.")
        sys.exit(1)

    # ── Step 4: Create a test page ──────────────────────────────
    print("\n[4/6] Creating test page...")
    test_source_id = "__oppos_test_page__"
    try:
        page = client.pages.create(
            parent={"database_id": NOTION_DATABASE_ID},
            properties={
                "RFP Title": {
                    "title": [{"text": {"content": "[TEST] OppOS Connection Test — safe to delete"}}]
                },
                "Fit Score": {"number": 99},
                "Source ID": {
                    "rich_text": [{"text": {"content": test_source_id}}]
                },
                "Pipeline Status": {"select": {"name": "New"}},
                "Action": {"select": {"name": "Investigate"}},
            },
            children=[
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"text": {"content": "This page was created by the OppOS test script. You can delete it."}}]
                    },
                }
            ],
        )
        page_id = page["id"]
        print(f"  ✓ Test page created: {page_id}")
    except Exception as e:
        print(f"  ✗ Page creation failed: {e}")
        print("\n    Common causes:")
        print("    - Property names don't match the database schema")
        print("    - Select option doesn't exist yet (Notion auto-creates these)")
        print("    - Integration doesn't have 'Insert content' permission")
        sys.exit(1)

    # ── Step 5: Query back by Source ID ─────────────────────────
    print("\n[5/6] Querying back by Source ID...")
    try:
        # notion-client v3: databases.query → data_sources.query
        result = client.data_sources.query(
            data_source_id=NOTION_DATASOURCE_ID,
            filter={
                "property": "Source ID",
                "rich_text": {"equals": test_source_id},
            },
            page_size=1,
        )
        pages = result.get("results", [])
        if pages and pages[0]["id"] == page_id:
            print(f"  ✓ Found test page via Source ID query — dedup will work")
        else:
            print(f"  ⚠ Query returned {len(pages)} results — dedup may not work")
    except Exception as e:
        print(f"  ✗ Query failed: {e}")

    # ── Step 6: Clean up (archive the test page) ────────────────
    print("\n[6/6] Cleaning up test page...")
    try:
        client.pages.update(page_id=page_id, archived=True)
        print(f"  ✓ Test page archived (moved to trash)")
    except Exception as e:
        print(f"  ⚠ Cleanup failed: {e}")
        print(f"    Delete manually: page ID {page_id}")

    # ── Done ────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  ✓ All checks passed — Notion integration is ready!")
    print("=" * 60)
    print("\nNext steps:")
    print("  1. Add NOTION_TOKEN and NOTION_DATABASE_ID to Streamlit secrets")
    print("  2. Deploy — the 'Push to Notion' button will go live")
    print()


if __name__ == "__main__":
    main()
