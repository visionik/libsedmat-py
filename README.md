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

## Implementing a Custom Backend

Implement the `libsedmat.Backend` `Protocol` (`project`, `apply_text_plan`, `apply_address_mutations`, `apply_transliterate`, `apply_container_op`) to connect SEDMAT to python-docx, python-pptx, Google Docs, or any rich document target. All offsets are UTF-16 code units.

## Guide for AI Agents

- Inspect first via `backend.project()` → `format_structure(seg)` / `format_numbered(seg)` for exact 1-based indices.
- Validate scripts with `ExecuteOptions(dry_run=True)` before mutating.
- Honor `BraceExpression.no_reset` (`{!0}`) for additive formatting vs. implicit reset default.
- Conformance suite: `testdata/conformance/v3.6.json` (shared across Go, TS, Rust, Python, and C++).

## Development

```bash
make check   # pytest -v
```

## License

MIT — see [LICENSE](./LICENSE).
