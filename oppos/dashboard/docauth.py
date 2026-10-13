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
# Nutrient Web SDK (the PDF viewer) for the in-page preview of the exported PDF; assets load from this base.
VIEWER_VERSION = "1.23.0"
VIEWER_BASE = f"https://cdn.cloud.pspdfkit.com/pspdfkit-web@{VIEWER_VERSION}/"


def _streamlit_version() -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in st.__version__.split(".")[:2])
    except Exception:
        return (0, 0)


EDITOR_REV = "5"  # bump when docauth.html changes so browsers do not serve a cached copy


def response_editor(markdown: str, file_stem: str, license_key: str = "", height: int = 760, viewer_license_key: str = "") -> None:
    """Mount the Document Authoring editor with `markdown` loaded; downloads use `file_stem`. "Preview PDF" renders the
    export in Nutrient Web SDK (licensed with `viewer_license_key`, trial watermark without it).

    One component frame carries the payload (as a JSON script tag) and creates the editor iframe itself, at a URL
    resolved against the app page's own path: Streamlit Community Cloud serves the app under a prefix
    (`/~/+/…`) and answers the bare `/app/static/…` path with its loading shell, which never shows the page.
    The editor page is a real URL (not srcdoc) so its hostname is set and the licence can validate, and it
    reads the payload from this parent frame — never from the URL, which browsers cap at ~2 MB.
    """
    if _streamlit_version() < MIN_STREAMLIT:
        st.error(f"The response editor needs Streamlit {MIN_STREAMLIT[0]}.{MIN_STREAMLIT[1]}+ (static pages are served as text/html); "
                 f"this is {st.__version__}. Upgrade Streamlit.")
        return
    payload = json.dumps({"md": markdown, "stem": file_stem, "licenseKey": license_key or "", "version": DOCAUTH_VERSION,
                          "viewerBase": VIEWER_BASE, "viewerLicenseKey": viewer_license_key or ""}, ensure_ascii=False)
    payload_id = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]
    rel = EDITOR_PATH.lstrip("/")
    components.html(
        f'<script type="application/json" data-oppos-payload="{payload_id}">{payload.replace("</", "<\\/")}</script>'
        f'<style>html,body{{margin:0;height:100%;background:#fff}}iframe{{width:100%;height:100%;border:0;display:block}}</style>'
        f'<script>(function(){{'
        f'  var mount = function () {{'
        f'    var base = "/";'
        f'    try {{ base = window.parent.location.pathname.replace(/\\/[^\\/]*$/, "/"); }} catch (e) {{}}'
        f'    var f = document.createElement("iframe");'
        f'    f.src = new URL(base + "{rel}?v={DOCAUTH_VERSION}&r={EDITOR_REV}&p={payload_id}", window.parent.location.href).href;'
        f'    f.title = "Response document";'
        f'    (document.body || document.documentElement).appendChild(f);'
        f'  }};'
        f'  if (document.body) mount(); else document.addEventListener("DOMContentLoaded", mount);'  # the component template may run us before <body>
        f'}})();</script>',
        height=height,
    )
