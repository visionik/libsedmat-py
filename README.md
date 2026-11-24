# libsedmat-py

Zero-dependency Python library implementing **[SEDMAT](https://sedmat.org)** (*Sed-Expression-Driven Mark(up|down) Annotation & Transformation*, **v3.6 + v3.7 `@` container scopes**).

For full language syntax, flags, and container scope documentation, see **[sedmat.org](https://sedmat.org)** and [`visionik/sedmat`](https://github.com/visionik/sedmat).

## Installation

```bash
pip install libsedmat
# or
uv add libsedmat
```

Requires Python 3.10+. **Zero runtime dependencies.**

## Quick Start

```python
from libsedmat import ExecuteOptions, Executor, MemoryDocument, format_numbered, select_segment

doc = MemoryDocument(
    "Draft Proposal",
    "Critical warning in paragraph two",
    "Temporary note to remove",
)

script = """
1s/Draft/{h=1}Final/
2s/warning/{b c=red}/
$d
$a/Appendix A/
"""

ex = Executor(doc)
preview = ex.execute_string(script, ExecuteOptions(dry_run=True))
print(f"Dry-run matched {preview.total_matches} operations")

ex.execute_string(script)
print(format_numbered(select_segment(doc.project())))
```

## SEDMAT v3.7 Container Scopes (`@`)

Target slides, sheets, tabs, pages, headers/footers, and named regions (`title`, `sub`, `body`, `notes`, `shape=N`):

```python
from libsedmat import parse_program

prog = parse_program("""
@1:{z=#0F172A transition=fade}
@slide=2:title:s/.*/{c=navy}New Title/
@2:notes:a/Pause for Q&A./
@"Q4 Budget":s/USD/EUR/g
@$a/{layout=two-col}Next Steps/
@3{move=1}
""")
```

## IntelliSense, Diagnostics & Syntax Tokenizer

`libsedmat-py` includes a UI-agnostic, zero-dependency IntelliSense engine for editor command bars, TUIs, CLIs, and LSPs:

```python
from libsedmat import ContextInfo, extract_diagnostic, get_completions, tokenize_sedmat

# 1. Cursor-aware completions with capability profiles & host extensions
res = get_completions("s/foo/{c=re", 11, ContextInfo(mode="slides", active_container=2))
# res.suggestions[0].label == "red", swatch == "#FF0000"
# res.ghost_suffix == "d"

# 2. Non-throwing syntax tokenizer
tokens = tokenize_sedmat("@2:title:s/foo/{b c=red}bar/gi")

# 3. Structured diagnostics from any exception or message
diag = extract_diagnostic(ValueError("SEDMAT error at offset 9: Unclosed brace — add '}'"))
```

## Implementing a Custom Backend

Implement the `libsedmat.Backend` `Protocol` (`project`, `apply_text_plan`, `apply_address_mutations`, `apply_transliterate`, `apply_container_op`) to connect SEDMAT to python-docx, python-pptx, Google Docs, or any rich document target. All offsets are UTF-16 code units.

## Guide for AI Agents

- Inspect first via `backend.project()` → `format_structure(seg)` / `format_numbered(seg)` for exact 1-based indices.
- Validate scripts with `ExecuteOptions(dry_run=True)` before mutating.
- Honor `BraceExpression.no_reset` (`{!0}`) for additive formatting vs. implicit reset default.
- Conformance suite: `testdata/conformance/v3.6.json` (shared across Go, TS, Rust, Python, and C++).

## Examples

All examples have **zero external dependencies** (Python 3.10+ stdlib only):

- **[`examples/lsp_server.py`](./examples/lsp_server.py)** — SEDMAT Language Server (LSP over stdio) with live diagnostics, profile-aware completions + color swatches, signature help, and semantic tokens:
  ```bash
  PYTHONPATH=src python3 examples/lsp_server.py
  ```
- **[`examples/doc_playground.py`](./examples/doc_playground.py)** — Launch-a-web Document Playground (`http://127.0.0.1:4173`) with live syntax highlighting, IntelliSense dropdown, color swatches, ghost text, dry-run preview, and numbered document view:
  ```bash
  PYTHONPATH=src python3 examples/doc_playground.py
  ```
- **[`examples/slide_deck.py`](./examples/slide_deck.py)** — Launch-a-web Slide Deck Studio (`http://127.0.0.1:4174`) demonstrating SEDMAT v3.7 `@` container scopes and Slides profile completions:
  ```bash
  PYTHONPATH=src python3 examples/slide_deck.py
  ```

## Development

```bash
make check   # pytest -v (72 tests)
```

## Related

- **SEDMAT Website & Docs**: [https://sedmat.org](https://sedmat.org)
- **SEDMAT Specification**: [https://github.com/visionik/sedmat](https://github.com/visionik/sedmat)
- **Sibling Libraries**: [`libsedmat-go`](https://github.com/visionik/libsedmat-go) · [`libsedmat-ts`](https://github.com/visionik/libsedmat-ts) · [`libsedmat-rs`](https://github.com/visionik/libsedmat-rs) · [`libsedmat-cpp`](https://github.com/visionik/libsedmat-cpp)

## License

MIT — see [LICENSE](./LICENSE).
