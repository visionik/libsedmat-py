#!/usr/bin/env python3
"""Launch-a-Web SEDMAT Document Playground (zero external dependencies).

Run: PYTHONPATH=src python3 examples/doc_playground.py
"""

from __future__ import annotations

import dataclasses
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from libsedmat import (
    ContextInfo,
    ExecuteOptions,
    Executor,
    MemoryDocument,
    extract_diagnostic,
    format_numbered,
    get_completions,
    select_segment,
    tokenize_sedmat,
)

HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>libsedmat-py — Document Playground</title>
  <style>
    :root { color-scheme: dark; font-family: ui-sans-serif, system-ui, sans-serif; }
    body { margin: 0; background: #0b1120; color: #e2e8f0; display: grid; place-items: center; min-height: 100vh; }
    .app { width: min(920px, 94vw); display: grid; gap: 16px; padding: 24px 0; }
    .card { background: #111827; border: 1px solid #1f2937; border-radius: 12px; padding: 16px; }
    .row { display: flex; gap: 8px; }
    input { flex: 1; background: #0f172a; color: #f8fafc; border: 1px solid #334155; border-radius: 8px; padding: 10px 12px; font-family: ui-monospace, monospace; font-size: 14px; }
    button { background: #2563eb; color: #fff; border: 0; border-radius: 8px; padding: 10px 16px; font-weight: 600; cursor: pointer; }
    button.sec { background: #334155; }
    .tokens { font-family: ui-monospace, monospace; font-size: 13px; margin-top: 8px; min-height: 20px; }
    .tok-scope { color: #c084fc; } .tok-address { color: #fbbf24; } .tok-command { color: #38bdf8; font-weight: 700; }
    .tok-pattern { color: #f472b6; } .tok-brace { color: #4ade80; } .tok-flag { color: #fb923c; } .tok-delimiter { color: #64748b; }
    .ok { color: #4ade80; } .err { color: #f87171; }
    .sugs { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
    .sug { background: #1e293b; border: 1px solid #334155; color: #e2e8f0; border-radius: 6px; padding: 4px 8px; font-size: 12px; cursor: pointer; display: inline-flex; align-items: center; gap: 6px; }
    .swatch { width: 10px; height: 10px; border-radius: 2px; border: 1px solid #475569; }
    pre { margin: 0; white-space: pre-wrap; font-family: ui-monospace, monospace; font-size: 14px; line-height: 1.6; }
  </style>
</head>
<body>
  <div class="app">
    <h1 style="margin:0;font-size:20px;">libsedmat-py — Document Playground (Zero-Dep Python stdlib)</h1>
    <div class="card">
      <div class="row">
        <input id="cmd" value="2s/TODO/{b c=red}/g" />
        <button id="apply">Apply</button>
        <button id="reset" class="sec">Reset</button>
      </div>
      <div id="tokens" class="tokens"></div>
      <div id="status" style="font-size:13px;margin-top:8px;"></div>
      <div id="sugs" class="sugs"></div>
    </div>
    <div class="card">
      <h3 style="margin:0 0 10px;font-size:13px;color:#94a3b8;text-transform:uppercase;">Numbered Document (cat -N)</h3>
      <pre id="doc"></pre>
    </div>
  </div>
  <script>
    const cmd = document.getElementById("cmd");
    async function refresh() {
      const r = await fetch("/api/state").then(x => x.json());
      document.getElementById("doc").textContent = r.numbered;
    }
    async function inspect() {
      const input = cmd.value, cursor = cmd.selectionStart ?? input.length;
      const r = await fetch("/api/inspect", { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({input, cursor}) }).then(x => x.json());
      document.getElementById("tokens").innerHTML = r.tokens.map(t => '<span class="tok-'+t.kind+'">'+t.text.replace(/[<>&]/g,c=>({'<':'&lt;','>':'&gt;','&':'&amp;'}[c]))+'</span>').join("") + (r.completions.ghost_suffix ? '<span style="opacity:.4">'+r.completions.ghost_suffix+'</span>' : "");
      const st = document.getElementById("status");
      st.className = r.diagnostic.ok ? "ok" : "err";
      st.textContent = (r.diagnostic.ok ? "✓ " : "✗ ") + r.diagnostic.summary + (r.diagnostic.hint ? " — " + r.diagnostic.hint : "");
      const sugs = document.getElementById("sugs");
      sugs.innerHTML = "";
      for (const s of r.completions.suggestions.slice(0, 8)) {
        const b = document.createElement("button");
        b.className = "sug";
        b.innerHTML = (s.swatch ? '<span class="swatch" style="background:'+s.swatch+'"></span>' : '') + '<strong>'+s.label+'</strong> <span style="opacity:.7">'+s.detail+'</span>';
        b.onclick = () => { cmd.value = input.slice(0, s.replace_from) + s.insert_text + input.slice(s.replace_to); cmd.focus(); inspect(); };
        sugs.appendChild(b);
      }
    }
    document.getElementById("apply").onclick = async () => {
      await fetch("/api/apply", { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({input: cmd.value}) });
      await refresh(); await inspect();
    };
    document.getElementById("reset").onclick = async () => { await fetch("/api/reset", { method: "POST" }); await refresh(); };
    cmd.addEventListener("input", inspect);
    cmd.addEventListener("keyup", inspect);
    refresh(); inspect();
  </script>
</body>
</html>"""


def initial_doc() -> MemoryDocument:
    return MemoryDocument(
        "SEDMAT v3.7 Interactive Document",
        "This paragraph contains a TODO item and a critical warning.",
        "DRAFT: delete this scratch note with 3d or d/DRAFT/",
        "Closing summary ready for formatting and appends.",
    )


DOC = initial_doc()


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, code: int, obj: object) -> None:
        raw = json.dumps(obj, default=dataclasses.asdict).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length).decode("utf-8")) if length else {}

    def do_GET(self) -> None:
        if self.path == "/":
            raw = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        elif self.path == "/api/state":
            self._send_json(200, {"numbered": format_numbered(select_segment(DOC.project()))})
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        global DOC
        if self.path == "/api/reset":
            DOC = initial_doc()
            self._send_json(200, {"ok": True})
        elif self.path == "/api/inspect":
            body = self._read_json()
            text = str(body.get("input", ""))
            cursor = int(body.get("cursor", len(text)))
            comp = get_completions(text, cursor, ContextInfo(mode="document"))
            toks = tokenize_sedmat(text)
            diag = {"ok": True, "summary": "Ready", "hint": None}
            if text.strip():
                try:
                    rep = Executor(DOC).execute_string(text, ExecuteOptions(dry_run=True))
                    diag = {"ok": True, "summary": f"Dry-run matched {rep.total_matches} operation(s)", "hint": None}
                except Exception as exc:
                    diag = dataclasses.asdict(extract_diagnostic(exc))
            self._send_json(200, {"completions": comp, "tokens": toks, "diagnostic": diag})
        elif self.path == "/api/apply":
            body = self._read_json()
            try:
                rep = Executor(DOC).execute_string(str(body.get("input", "")))
                self._send_json(200, {"ok": True, "matches": rep.total_matches, "numbered": format_numbered(select_segment(DOC.project()))})
            except Exception as exc:
                self._send_json(400, {"ok": False, "diagnostic": extract_diagnostic(exc)})
        else:
            self.send_error(404)


def main() -> None:
    port = int(os.environ.get("PORT", "4173"))
    print(f"SEDMAT Python Document Playground running at http://127.0.0.1:{port}")
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
