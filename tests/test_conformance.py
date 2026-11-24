from __future__ import annotations

import json
from pathlib import Path

import pytest

from libsedmat import (
    ExecuteOptions,
    Executor,
    MemoryDocument,
    SedmatError,
    enrich,
    format_numbered,
    format_structure,
    parse,
    parse_file,
    select_segment,
)

ROOT = Path(__file__).resolve().parent.parent
SUITE = json.loads((ROOT / "testdata" / "conformance" / "v3.6.json").read_text(encoding="utf-8"))
FIXTURES = sorted((ROOT / "testdata" / "fixtures").glob("*.sed"))


@pytest.mark.parametrize("tc", SUITE["parse_vectors"], ids=lambda tc: tc["name"])
def test_conformance_parse_vectors(tc: dict) -> None:
    if tc.get("want_error"):
        with pytest.raises(SedmatError):
            enrich(parse(tc["input"]))
        return

    prog = enrich(parse(tc["input"]))
    assert len(prog.expressions) == 1
    expr = prog.expressions[0]

    if "command" in tc:
        assert expr.command == tc["command"]
    if "pattern" in tc:
        assert expr.pattern == tc["pattern"]
    if "replacement" in tc:
        assert expr.replacement == tc["replacement"]
    if "global" in tc:
        assert expr.global_flag == tc["global"]
    if "nth" in tc:
        assert expr.nth_match == tc["nth"]
    if "address" in tc:
        assert expr.address is not None
        assert expr.address.start == tc["address"]["start"]
        assert expr.address.end == tc["address"]["end"]
        assert expr.address.has_range == tc["address"]["has_range"]
    if "expect_span_count" in tc:
        assert len(expr.brace_spans) == tc["expect_span_count"]
    if "expect_table_create" in tc:
        assert expr.table_create is not None
        assert expr.table_create.rows == tc["expect_table_create"]["rows"]
        assert expr.table_create.columns == tc["expect_table_create"]["columns"]
    if "expect_brace" in tc:
        b = expr.brace
        assert b is not None
        eb = tc["expect_brace"]
        if "bold" in eb:
            assert b.bold == eb["bold"]
        if "color" in eb:
            assert b.color is not None and b.color.upper() == eb["color"].upper()
        if eb.get("reset"):
            assert b.reset is True
        if eb.get("no_reset"):
            assert b.no_reset is True
        if eb.get("has_break"):
            assert b.has_break is True
            assert b.break_kind == eb["break"]
        if "cols" in eb:
            assert b.cols == eb["cols"]
        if eb.get("check_set"):
            assert b.check is not None
        if "toc" in eb:
            assert b.toc == eb["toc"]
        if "comment" in eb:
            assert b.comment == eb["comment"]
        if "bookmark" in eb:
            assert b.bookmark == eb["bookmark"]
        if "url" in eb:
            assert b.url == eb["url"]
        if "img_ref" in eb:
            assert b.img_ref == eb["img_ref"]


@pytest.mark.parametrize("tc", SUITE["execution_vectors"], ids=lambda tc: tc["name"])
def test_conformance_execution_vectors(tc: dict) -> None:
    doc = MemoryDocument(*tc["paragraphs"])
    ex = Executor(doc)
    if tc.get("want_error"):
        with pytest.raises(SedmatError):
            ex.execute_string(tc["script"])
        return
    ex.execute_string(tc["script"])
    assert doc.paragraph_texts() == tc["expected_paragraphs"]


@pytest.mark.parametrize("fixture_path", FIXTURES, ids=lambda p: p.name)
def test_ported_sed_fixtures(fixture_path: Path) -> None:
    prog = parse_file(fixture_path)
    assert len(prog.expressions) > 0


def test_v37_container_scopes_dry_run_and_introspection() -> None:
    doc = MemoryDocument("Slide 1 Title", "Draft subtitle")
    doc.tabs[0].id = "slide-1"
    doc.tabs[0].title = "Intro"
    doc.add_tab("slide-2", "Metrics", "Latency is 500ms", "Keep line")
    doc.add_tab("slide-3", "Q4 Budget", "Total in USD")

    ex = Executor(doc)
    dry = ex.execute_string("@2:s/500ms/120ms/", ExecuteOptions(dry_run=True))
    assert dry.dry_run is True
    assert dry.total_matches == 1
    assert doc.paragraph_texts("slide-2")[0] == "Latency is 500ms"

    ex.execute_string(
        """
@1:{z=#0F172A transition=fade}
@2:s/500ms/{b c=green}120ms/g
@2:{notes="Highlight 120ms WebTransport benchmark"}
@"Q4 Budget":s/USD/EUR/g
@$a/Next Steps/
@4{hide}
"""
    )
    assert doc.tabs[0].background == "#0F172A"
    assert doc.tabs[0].transition == "fade"
    assert doc.paragraph_texts("slide-2") == ["Latency is 120ms", "Keep line"]
    assert doc.tabs[1].notes == "Highlight 120ms WebTransport benchmark"
    assert doc.paragraph_texts("Q4 Budget") == ["Total in EUR"]
    assert len(doc.tabs) == 4
    assert doc.tabs[3].hidden is True

    seg = select_segment(doc.project(), "slide-2")
    assert '[1] paragraph (NORMAL_TEXT): "Latency is 120ms"' in format_structure(seg)
    assert "[2] Keep line" in format_numbered(seg)
