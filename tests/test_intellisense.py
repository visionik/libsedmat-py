from libsedmat import (
    ContextInfo,
    FlagDefinition,
    IntelliSenseExtensions,
    ValueOption,
    extract_diagnostic,
    get_completions,
    tokenize_sedmat,
)


def test_extract_diagnostic_with_offset_and_hint():
    diag = extract_diagnostic(
        ValueError("SEDMAT error at offset 9: Unclosed brace expression — add a closing '}'")
    )
    assert not diag.ok
    assert diag.error_offset == 9
    assert diag.error_length == 1
    assert diag.summary == "Unclosed brace expression"
    assert diag.hint == "add a closing '}'"

    plain = extract_diagnostic(RuntimeError("bad syntax"))
    assert plain.error_offset is None
    assert plain.summary == "bad syntax"


def test_completions_profiles_and_ghost_suffix():
    doc = get_completions("s/foo/{", 7)
    assert any(s.label == "b" for s in doc.suggestions)
    assert not any(s.label == "transition=" for s in doc.suggestions)

    slides_ctx = ContextInfo(mode="slides", active_container=3)
    slides = get_completions("s/foo/{tr", 9, slides_ctx)
    assert any(s.label == "transition=" for s in slides.suggestions)

    at_res = get_completions("@", 1, slides_ctx)
    assert any(s.label == "@3:title:" for s in at_res.suggestions)
    assert at_res.ghost_suffix == "3:"


def test_completions_canonical_color_swatches():
    res = get_completions("s/foo/{c=", 9)
    swatches = {s.label: s.swatch for s in res.suggestions}
    assert swatches["green"] == "#00FF00"
    assert swatches["orange"] == "#FF8C00"
    assert swatches["red"] == "#FF0000"


def test_completions_semicolon_chaining_and_extensions():
    chained = get_completions("s/a/b/g; s/c/{c=re", 18)
    assert any(s.label == "red" for s in chained.suggestions)
    assert chained.ghost_suffix == "d"

    ext = IntelliSenseExtensions(
        flags=[FlagDefinition("brand=", "brand=", "Custom brand flag")],
        values={"brand": [ValueOption("acme", "Acme primary", "#123456")]},
    )
    ctx = ContextInfo(mode="document", extensions=ext)

    flag_res = get_completions("s/x/{br", 7, ctx)
    assert flag_res.suggestions[0].label == "brand="

    val_res = get_completions("s/x/{brand=", 11, ctx)
    assert val_res.suggestions[0].label == "acme"
    assert val_res.suggestions[0].swatch == "#123456"


def test_tokenize_sedmat_lossless_and_non_throwing():
    expr = "@2:title:s/foo/{b c=red}bar/gi"
    tokens = tokenize_sedmat(expr)
    assert "".join(t.text for t in tokens) == expr
    kinds = [(t.kind, t.text) for t in tokens]
    assert ("scope", "@2:title:") in kinds
    assert ("command", "s") in kinds
    assert ("pattern", "foo") in kinds
    assert ("brace", "{b c=red}") in kinds
    assert ("text", "bar") in kinds
    assert ("flag", "gi") in kinds

    incomplete = "# comment\n@1:s/unclosed/{b c="
    inc_tokens = tokenize_sedmat(incomplete)
    assert "".join(t.text for t in inc_tokens) == incomplete
    assert inc_tokens[0].kind == "comment"
