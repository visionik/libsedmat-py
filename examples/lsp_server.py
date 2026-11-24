#!/usr/bin/env python3
"""Zero-dependency SEDMAT Language Server (LSP over stdio).

Run: PYTHONPATH=src python3 examples/lsp_server.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from libsedmat import (
    ContextInfo,
    extract_diagnostic,
    get_completions,
    parse_expression,
    tokenize_sedmat,
)

TOKEN_TYPES = [
    "comment",
    "scope",
    "address",
    "command",
    "delimiter",
    "pattern",
    "brace",
    "text",
    "flag",
    "whitespace",
]

LSP_TOKEN_LEGEND = [
    "comment",
    "namespace",
    "number",
    "keyword",
    "operator",
    "regexp",
    "decorator",
    "string",
    "modifier",
    "variable",
]


def send_message(payload: Dict[str, Any]) -> None:
    body = json.dumps({"jsonrpc": "2.0", **payload}).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    sys.stdout.buffer.write(header + body)
    sys.stdout.buffer.flush()


def read_message() -> Optional[Dict[str, Any]]:
    content_length = -1
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        stripped = line.decode("ascii", errors="ignore").strip()
        if not stripped:
            break
        if stripped.lower().startswith("content-length:"):
            content_length = int(stripped.split(":", 1)[1].strip())
    if content_length < 0:
        return None
    body = sys.stdin.buffer.read(content_length)
    if len(body) < content_length:
        return None
    return json.loads(body.decode("utf-8"))


def kind_to_lsp(kind: str) -> int:
    return {"scope": 9, "command": 14, "flag": 10, "value": 12, "snippet": 15}.get(kind, 15)


def offset_to_line_char(text: str, offset: int) -> Tuple[int, int]:
    safe = max(0, min(len(text), offset))
    line = text.count("\n", 0, safe)
    last_nl = text.rfind("\n", 0, safe)
    return line, safe - (last_nl + 1)


def publish_diagnostics(uri: str, text: str) -> None:
    diags: List[Dict[str, Any]] = []
    for idx, line in enumerate(text.split("\n")):
        trimmed = line.strip()
        if not trimmed or trimmed.startswith("#"):
            continue
        try:
            parse_expression(trimmed)
        except Exception as exc:
            diag = extract_diagnostic(exc)
            col = diag.error_offset or 0
            length = max(1, diag.error_length or 1)
            msg = f"{diag.summary} — {diag.hint}" if diag.hint else diag.summary
            diags.append(
                {
                    "range": {
                        "start": {"line": idx, "character": col},
                        "end": {"line": idx, "character": col + length},
                    },
                    "severity": 1,
                    "source": "libsedmat-py",
                    "message": msg,
                }
            )
    send_message({"method": "textDocument/publishDiagnostics", "params": {"uri": uri, "diagnostics": diags}})


def encode_semantic_tokens(text: str) -> List[int]:
    tokens = tokenize_sedmat(text)
    data: List[int] = []
    prev_line, prev_char = 0, 0
    for tok in tokens:
        if tok.kind == "whitespace" or "\n" in tok.text:
            continue
        line, ch = offset_to_line_char(text, tok.start)
        delta_line = line - prev_line
        delta_start = ch - prev_char if delta_line == 0 else ch
        type_idx = TOKEN_TYPES.index(tok.kind) if tok.kind in TOKEN_TYPES else 0
        data.extend([delta_line, delta_start, tok.end - tok.start, type_idx, 0])
        prev_line, prev_char = line, ch
    return data


def main() -> None:
    docs: Dict[str, str] = {}
    shutdown_requested = False

    while True:
        msg = read_message()
        if msg is None:
            return
        msg_id = msg.get("id")
        method = msg.get("method")
        params = msg.get("params") or {}

        if method == "initialize":
            send_message(
                {
                    "id": msg_id,
                    "result": {
                        "capabilities": {
                            "textDocumentSync": 1,
                            "completionProvider": {"triggerCharacters": ["{", "@", "/", "=", ":", " "]},
                            "signatureHelpProvider": {"triggerCharacters": ["/", "{", "="]},
                            "semanticTokensProvider": {
                                "legend": {"tokenTypes": LSP_TOKEN_LEGEND, "tokenModifiers": []},
                                "full": True,
                            },
                        },
                        "serverInfo": {"name": "libsedmat-py-lsp", "version": "0.1.0"},
                    },
                }
            )
        elif method == "initialized":
            pass
        elif method == "shutdown":
            shutdown_requested = True
            send_message({"id": msg_id, "result": None})
        elif method == "exit":
            sys.exit(0 if shutdown_requested else 1)
        elif method == "textDocument/didOpen":
            td = params.get("textDocument") or {}
            uri, text = td.get("uri"), td.get("text", "")
            if uri:
                docs[uri] = text
                publish_diagnostics(uri, text)
        elif method == "textDocument/didChange":
            uri = (params.get("textDocument") or {}).get("uri")
            changes = params.get("contentChanges") or []
            if uri and changes:
                text = str(changes[-1].get("text", ""))
                docs[uri] = text
                publish_diagnostics(uri, text)
        elif method == "textDocument/completion":
            uri = (params.get("textDocument") or {}).get("uri", "")
            pos = params.get("position") or {}
            line_idx = int(pos.get("line", 0))
            char_idx = int(pos.get("character", 0))
            lines = docs.get(uri, "").split("\n")
            line_text = lines[line_idx] if 0 <= line_idx < len(lines) else ""
            res = get_completions(line_text, char_idx, ContextInfo(mode="all"))
            items = [
                {
                    "label": s.label,
                    "kind": kind_to_lsp(s.kind),
                    "detail": f"{s.detail} ({s.swatch})" if s.swatch else s.detail,
                    "textEdit": {
                        "range": {
                            "start": {"line": line_idx, "character": s.replace_from},
                            "end": {"line": line_idx, "character": s.replace_to},
                        },
                        "newText": s.insert_text,
                    },
                }
                for s in res.suggestions
            ]
            send_message({"id": msg_id, "result": {"isIncomplete": False, "items": items}})
        elif method == "textDocument/signatureHelp":
            uri = (params.get("textDocument") or {}).get("uri", "")
            pos = params.get("position") or {}
            line_idx = int(pos.get("line", 0))
            char_idx = int(pos.get("character", 0))
            lines = docs.get(uri, "").split("\n")
            line_text = lines[line_idx] if 0 <= line_idx < len(lines) else ""
            res = get_completions(line_text, char_idx, ContextInfo(mode="all"))
            label = "".join(p.text for p in res.signature)
            active_idx = next((i for i, p in enumerate(res.signature) if p.active), 0)
            send_message(
                {
                    "id": msg_id,
                    "result": {
                        "signatures": [
                            {
                                "label": label,
                                "documentation": res.context_title,
                                "parameters": [{"label": p.text} for p in res.signature],
                            }
                        ],
                        "activeSignature": 0,
                        "activeParameter": active_idx,
                    },
                }
            )
        elif method == "textDocument/semanticTokens/full":
            uri = (params.get("textDocument") or {}).get("uri", "")
            send_message({"id": msg_id, "result": {"data": encode_semantic_tokens(docs.get(uri, ""))}})
        elif msg_id is not None:
            send_message({"id": msg_id, "error": {"code": -32601, "message": f"Method not found: {method}"}})


if __name__ == "__main__":
    main()
