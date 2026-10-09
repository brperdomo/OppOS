"""In-app response editor built on the Nutrient Document Authoring SDK.

The dashboard hands the response Markdown to the SDK running in the browser (Streamlit component
iframe): the SDR edits it in the WYSIWYG editor and downloads DOCX, PDF or PDF/A. Nothing is
uploaded — the engine runs client-side; only the CDN bundle and fonts are fetched.
"""

from __future__ import annotations

import json

import streamlit.components.v1 as components

DOCAUTH_VERSION = "1.22.1"
DOCAUTH_CDN = f"https://document-authoring.cdn.nutrient.io/releases/document-authoring-{DOCAUTH_VERSION}-umd.js"

_HTML = """<!doctype html>
<html><head><meta charset="utf-8">
<style>
  html, body {{ margin: 0; height: 100%; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #fff; }}
  body {{ display: flex; flex-direction: column; }}
  /* The SDK draws its own toolbar at the top of the editor; ours sits underneath the page. */
  .bar {{ display: flex; gap: 8px; align-items: center; padding: 8px 10px; border-top: 1px solid #e5e7eb; background: #f9fafb; flex: 0 0 auto; }}
  .bar button {{ padding: 6px 12px; border: 1px solid #d1d5db; border-radius: 6px; background: #fff; cursor: pointer; font-size: 13px; }}
  .bar button:hover {{ background: #f3f4f6; }}
  .bar button:disabled {{ opacity: .5; cursor: default; }}
  .status {{ margin-left: auto; font-size: 12px; color: #6b7280; }}
  #editor {{ flex: 1 1 auto; min-height: 0; position: relative; }}
</style></head>
<body>
<div id="editor"></div>
<div class="bar">
  <button id="docx" disabled>⬇ DOCX</button>
  <button id="pdf" disabled>⬇ PDF</button>
  <button id="pdfa" disabled>⬇ PDF/A</button>
  <span class="status" id="status">Loading Nutrient Document Authoring…</span>
</div>
<script type="application/json" id="cfg">{payload}</script>
<script src="{cdn}"></script>
<script>
(async () => {{
  const cfg = JSON.parse(document.getElementById('cfg').textContent);
  const status = document.getElementById('status');
  try {{
    const opts = cfg.licenseKey ? {{ licenseKey: cfg.licenseKey }} : {{}};
    const system = await DocAuth.createDocAuthSystem(opts);
    const doc = await system.import(new TextEncoder().encode(cfg.md), {{ format: 'markdown', fileName: cfg.stem + '.md' }});
    const editor = await system.createEditor(document.getElementById('editor'), {{ document: doc }});
    const save = async (format, ext, mime, extra) => {{
      status.textContent = 'Exporting ' + ext.toUpperCase() + '…';
      try {{
        const buf = await editor.currentDocument().export(Object.assign({{ format }}, extra || {{}}));
        const url = URL.createObjectURL(new Blob([buf], {{ type: mime }}));
        const a = document.createElement('a'); a.href = url; a.download = cfg.stem + '.' + ext; a.click();
        setTimeout(() => URL.revokeObjectURL(url), 2000);
        status.textContent = ext.toUpperCase() + ' downloaded';
      }} catch (e) {{ status.textContent = 'Export failed: ' + e.message; }}
    }};
    document.getElementById('docx').onclick = () => save('docx', 'docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document');
    document.getElementById('pdf').onclick = () => save('pdf', 'pdf', 'application/pdf');
    document.getElementById('pdfa').onclick = () => save('pdf', 'pdf', 'application/pdf', {{ PDF_A: true }});
    for (const id of ['docx', 'pdf', 'pdfa']) document.getElementById(id).disabled = false;
    status.textContent = cfg.licenseKey ? 'Ready' : 'Ready (evaluation build — exports carry a watermark until DOCAUTH_LICENSE_KEY is set)';
  }} catch (e) {{
    status.textContent = 'Could not start the editor: ' + e.message;
  }}
}})();
</script>
</body></html>"""


def response_editor(markdown: str, file_stem: str, license_key: str = "", height: int = 760) -> None:
    """Mount the Document Authoring editor with `markdown` loaded; downloads use `file_stem`."""
    payload = json.dumps({"md": markdown, "stem": file_stem, "licenseKey": license_key or ""}).replace("</", "<\\/")
    components.html(_HTML.format(payload=payload, cdn=DOCAUTH_CDN), height=height, scrolling=False)
