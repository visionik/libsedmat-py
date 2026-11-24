# Changelog

All notable changes to `libsedmat-py` will be documented in this file.

## [0.1.0] - 2026-11-24

### Added
- Zero-dependency pure-Python implementation of SEDMAT v3.6 + v3.7 (`@` container scopes and slide/shape brace flags).
- Full parser, semantic enricher, canonical `{flags}` brace DSL (`{0}` reset and `{!0}` additive no-reset), UTF-16 planners, `format_structure` / `format_numbered`, `Backend` protocol, `Executor` (with `dry_run`), and `MemoryDocument`.
- Full pytest conformance suite verifying `testdata/conformance/v3.6.json`, ported `v7`–`v12` `.sed` fixtures, and v3.7 container scopes.
