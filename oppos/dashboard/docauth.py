"""In-app response editor built on the Nutrient Document Authoring SDK.

The dashboard hands the response Markdown to the SDK running in the browser: the SDR edits it in
the WYSIWYG editor and downloads DOCX, PDF or PDF/A. Nothing is uploaded — the engine runs
client-side; only the CDN bundle and fonts are fetched.

The editor page is served from ``oppos/dashboard/static/docauth.html`` (Streamlit static serving,
``server.enableStaticServing = true``) rather than as a ``srcdoc`` component: a srcdoc iframe
has an empty hostname, and a Document Authoring license is bound to the app's domain. The payload
travels in the URL fragment, which the browser never sends to the server.
"""

from __future__ import annotations

import base64
import json

import streamlit.components.v1 as components

DOCAUTH_VERSION = "1.22.1"
DOCAUTH_CDN = f"https://document-authoring.cdn.nutrient.io/releases/document-authoring-{DOCAUTH_VERSION}-umd.js"
EDITOR_PATH = "/app/static/docauth.html"


def response_editor(markdown: str, file_stem: str, license_key: str = "", height: int = 760) -> None:
    """Mount the Document Authoring editor with `markdown` loaded; downloads use `file_stem`."""
    payload = json.dumps({"md": markdown, "stem": file_stem, "licenseKey": license_key or "", "version": DOCAUTH_VERSION},
                         ensure_ascii=False).encode("utf-8")
    fragment = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    components.iframe(f"{EDITOR_PATH}?v={DOCAUTH_VERSION}#{fragment}", height=height, scrolling=False)
