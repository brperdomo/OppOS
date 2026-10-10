#!/usr/bin/env node
// Headless export of a response document with the Nutrient Document Authoring SDK.
//
//   npm install @nutrient-sdk/document-authoring        (Node 22 or 24)
//   node scripts/export_response.mjs response.md [--docx out.docx] [--pdf out.pdf] [--pdfa out-a.pdf]
//
// `response.md` is the Markdown the dashboard produces ("⬇ Markdown" in the Response document
// panel, or oppos.drafting.document.render_markdown). DOCAUTH_LICENSE_KEY removes the evaluation
// watermark.
import { createDocAuthSystem } from '@nutrient-sdk/document-authoring/node';
import { readFile, writeFile } from 'node:fs/promises';
import { basename } from 'node:path';

const args = process.argv.slice(2);
const input = args.find((a) => !a.startsWith('--'));
if (!input) {
  console.error('usage: export_response.mjs response.md [--docx out.docx] [--pdf out.pdf] [--pdfa out-a.pdf]');
  process.exit(2);
}
const opt = (flag, dflt) => {
  const i = args.indexOf(flag);
  return i < 0 ? null : args[i + 1] && !args[i + 1].startsWith('--') ? args[i + 1] : dflt;
};
const stem = basename(input).replace(/\.md$/i, '');
const targets = [
  ['docx', opt('--docx', `${stem}.docx`), {}],
  ['pdf', opt('--pdf', `${stem}.pdf`), {}],
  ['pdf', opt('--pdfa', `${stem}-pdfa.pdf`), { PDF_A: true }],
].filter(([, out]) => out);
if (!targets.length) targets.push(['docx', `${stem}.docx`, {}]);

const system = await createDocAuthSystem(process.env.DOCAUTH_LICENSE_KEY ? { licenseKey: process.env.DOCAUTH_LICENSE_KEY } : {});
try {
  const doc = await system.import(await readFile(input), { format: 'markdown', fileName: basename(input) });
  for (const [format, out, extra] of targets) {
    const buf = await doc.export({ format, ...extra });
    await writeFile(out, new Uint8Array(buf));
    console.log(`${out}  (${buf.byteLength.toLocaleString()} bytes)`);
  }
} finally {
  system.destroy();
}
