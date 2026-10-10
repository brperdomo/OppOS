"""In-app response editor built on the Nutrient Document Authoring SDK.

The dashboard hands the response Markdown to the SDK running in the browser: the SDR edits it in
the WYSIWYG editor and downloads DOCX, PDF or PDF/A. Nothing is uploaded — the engine runs
client-side; only the CDN bundle and fonts are fetched.

The editor page is served from ``oppos/dashboard/static/docauth.html`` (Streamlit static serving,
``server.enableStaticServing = true``) rather than as a ``srcdoc`` component: a srcdoc iframe
has an empty hostname, and a Document Authoring license is bound to the app's domain. The payload
is handed over through a same-origin sibling component (see response_editor), never through the URL.
"""

from __future__ import annotations

import hashlib
import json

import streamlit as st
import streamlit.components.v1 as components

# Static files are served as text/html from this version; 1.46 returned text/plain with nosniff, which the
# browser refuses to execute. requirements.txt pins the same floor.
MIN_STREAMLIT = (1, 57)

DOCAUTH_VERSION = "1.22.1"
DOCAUTH_CDN = f"https://document-authoring.cdn.nutrient.io/releases/document-authoring-{DOCAUTH_VERSION}-umd.js"
EDITOR_PATH = "/app/static/docauth.html"


def _streamlit_version() -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in st.__version__.split(".")[:2])
    except Exception:
        return (0, 0)


def response_editor(markdown: str, file_stem: str, license_key: str = "", height: int = 760) -> None:
    """Mount the Document Authoring editor with `markdown` loaded; downloads use `file_stem`.

    The payload (Markdown, licence key) is placed in a zero-height sibling component as a JSON script tag
    and read by the editor page through the shared origin — never in the URL, which browsers cap at ~2 MB
    while a large RFP's Markdown can exceed that.
    """
    if _streamlit_version() < MIN_STREAMLIT:
        st.error(f"The response editor needs Streamlit {MIN_STREAMLIT[0]}.{MIN_STREAMLIT[1]}+ (static pages are served as text/html); "
                 f"this is {st.__version__}. Download the Markdown instead, or upgrade Streamlit.")
        return
    payload = json.dumps({"md": markdown, "stem": file_stem, "licenseKey": license_key or "", "version": DOCAUTH_VERSION}, ensure_ascii=False)
    payload_id = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]
    components.html(f'<script type="application/json" data-oppos-payload="{payload_id}">{payload.replace("</", "<\\/")}</script>', height=0)
    components.iframe(f"{EDITOR_PATH}?v={DOCAUTH_VERSION}&p={payload_id}", height=height, scrolling=False)
