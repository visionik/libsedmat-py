#!/usr/bin/env python3
"""Launch-a-Web SEDMAT v3.7 Slide Deck Studio (zero external dependencies).

Run: PYTHONPATH=src python3 examples/slide_deck.py
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
    Executor,
    MemoryDocument,
    extract_diagnostic,
    get_completions,
)

HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>libsedmat-py — Slide Deck Studio</title>
  <style>
    :root { color-scheme: dark; font-family: ui-sans-serif, system-ui, sans-serif; }
    body { margin: 0; background: #020617; color: #f8fafc; padding: 24px; display: grid; gap: 16px; max-width: 960px; margin-inline: auto; }
    .stage { aspect-ratio: 16 / 9; border-radius: 16px; padding: 40px; display: flex; flex-direction: column; justify-content: center; border: 1px solid #334155; }
    .stage h2 { margin: 0 0 16px; font-size: 36px; }
    .stage li { font-size: 20px; margin: 8px 0; }
    .notes { background: #0f172a; padding: 12px 16px; border-radius: 8px; font-size: 14px; color: #94a3b8; }
    .bar { display: flex; gap: 8px; }
    input { flex: 1; background: #0f172a; color: #f8fafc; border: 1px solid #334155; border-radius: 8px; padding: 10px 12px; font-family: ui-monospace, monospace; }
    button { background: #2563eb; color: #fff; border: 0; border-radius: 8px; padding: 10px 16px; cursor: pointer; font-weight: 600; }
    .sugs { display: flex; flex-wrap: wrap; gap: 6px; }
    .sug { background: #1e293b; border: 1px solid #334155; color: #e2e8f0; border-radius: 6px; padding: 4px 8px; font-size: 12px; cursor: pointer; }
  </style>
</head>
<body>
  <h1 style="margin:0;font-size:20px;">libsedmat-py — Slide Deck Studio (v3.7 Container Scopes)</h1>
  <div id="stage" class="stage"></div>
  <div id="notes" class="notes"></div>
  <div class="bar">
    <input id="cmd" value="@2:s/145ms/95ms/g" />
    <button id="run">Run</button>
    <button id="prev" style="background:#334155">Prev</button>
    <button id="next" style="background:#334155">Next</button>
  </div>
  <div id="sugs" class="sugs"></div>
  <script>
    let idx = 0, deck = [];
    const cmd = document.getElementById("cmd");
    async function render() {
      deck = await fetch("/api/slides").then(r => r.json());
      const s = deck[idx] || deck[0];
      const stage = document.getElementById("stage");
      stage.style.background = s.background || "#0F172A";
      stage.innerHTML = "<h2>" + s.title + "</h2><ul>" + s.paragraphs.map(p => "<li>" + p + "</li>").join("") + "</ul>";
      document.getElementById("notes").textContent = "Speaker notes (" + (idx+1) + "/" + deck.length + "): " + (s.notes || "(none)");
    }
    async function complete() {
      const r = await fetch("/api/complete", { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({input: cmd.value, cursor: cmd.selectionStart ?? cmd.value.length, slide: idx+1}) }).then(x => x.json());
      const sugs = document.getElementById("sugs");
      sugs.innerHTML = "";
      for (const s of r.suggestions.slice(0, 6)) {
        const b = document.createElement("button");
        b.className = "sug";
        b.textContent = s.label + " — " + s.detail;
        b.onclick = () => { cmd.value = cmd.value.slice(0, s.replace_from) + s.insert_text + cmd.value.slice(s.replace_to); complete(); };
        sugs.appendChild(b);
      }
    }
    document.getElementById("run").onclick = async () => {
      await fetch("/api/apply", { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({script: cmd.value}) });
      await render();
    };
    document.getElementById("prev").onclick = () => { idx = Math.max(0, idx - 1); render(); complete(); };
    document.getElementById("next").onclick = () => { idx = Math.min(deck.length - 1, idx + 1); render(); complete(); };
    cmd.addEventListener("input", complete);
    render(); complete();
  </script>
</body>
</html>"""


def initial_deck() -> MemoryDocument:
    doc = MemoryDocument("Container-scoped editing with @1:, @2:, and @*:")
    doc.tabs[0].title = "SEDMAT v3.7 Slide Studio"
    doc.tabs[0].background = "#0F172A"
    doc.tabs[0].notes = "Welcome to the Python Slide Deck Studio."
    doc.add_tab("slide-2", "Architecture Benchmarks", ["Latency is 145ms across regions", "Zero external runtime dependencies"])
    doc.tabs[1].background = "#1E293B"
    doc.tabs[1].notes = "Highlight benchmark methodology."
    return doc


DECK = initial_deck()


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
        elif self.path == "/api/slides":
            slides = [
                {
                    "id": t.id,
                    "title": t.title,
                    "paragraphs": [p.text for p in t.paragraphs],
                    "notes": t.notes or "",
                    "background": t.background or "#0F172A",
                    "hidden": t.hidden,
                }
                for t in DECK.tabs
            ]
            self._send_json(200, slides)
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        if self.path == "/api/complete":
            body = self._read_json()
            text = str(body.get("input", ""))
            cursor = int(body.get("cursor", len(text)))
            slide = int(body.get("slide", 1))
            res = get_completions(text, cursor, ContextInfo(mode="slides", active_slide=slide, total_slides=len(DECK.tabs)))
            self._send_json(200, res)
        elif self.path == "/api/apply":
            body = self._read_json()
            try:
                Executor(DECK).execute_string(str(body.get("script", "")))
                self._send_json(200, {"ok": True})
            except Exception as exc:
                self._send_json(400, {"ok": False, "diagnostic": extract_diagnostic(exc)})
        else:
            self.send_error(404)


def main() -> None:
    port = int(os.environ.get("PORT", "4174"))
    print(f"SEDMAT Python Slide Deck Studio running at http://127.0.0.1:{port}")
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
