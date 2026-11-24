# Changelog

All notable changes to `libsedmat-py` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **UI-Agnostic IntelliSense, Diagnostics & Tokenizer (`src/libsedmat/intellisense.py`)**:
  - `get_completions` with capability profiles (`document`/`word`, `slides`, `spreadsheet`, `vector`, `timeline`, `all`), semicolon-chained command awareness, live grammar signatures, inline `ghost_suffix`, canonical `sedmat.org` color swatches, and host extension hooks (`IntelliSenseExtensions`).
  - `extract_diagnostic` returning structured error offset, span length, summary, and actionable hint.
  - `tokenize_sedmat` non-throwing lossless syntax tokenizer.

## [0.1.0] - 2026-11-24

### Added
- Zero-dependency pure-Python implementation of SEDMAT v3.6 + v3.7 (`@` container scopes and slide/shape brace flags).
- Full parser, semantic enricher, canonical `{flags}` brace DSL (`{0}` reset and `{!0}` additive no-reset), UTF-16 planners, `format_structure` / `format_numbered`, `Backend` protocol, `Executor` (with `dry_run`), and `MemoryDocument`.
- Full pytest conformance suite verifying `testdata/conformance/v3.6.json`, ported `v7`–`v12` `.sed` fixtures, and v3.7 container scopes.
