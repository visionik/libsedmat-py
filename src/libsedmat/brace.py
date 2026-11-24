from __future__ import annotations

import copy
import re

from .types import BraceExpression, BraceSpan, InlineSpan, SedmatError

NAMED_COLORS: dict[str, str] = {
    "red": "#FF0000",
    "green": "#008000",
    "blue": "#0000FF",
    "yellow": "#FFFF00",
    "orange": "#FFA500",
    "purple": "#800080",
    "pink": "#FFC0CB",
    "cyan": "#00FFFF",
    "aqua": "#00FFFF",
    "magenta": "#FF00FF",
    "white": "#FFFFFF",
    "black": "#000000",
    "gray": "#808080",
    "grey": "#808080",
    "navy": "#000080",
    "teal": "#008080",
    "maroon": "#800000",
    "olive": "#808000",
    "silver": "#C0C0C0",
    "lime": "#00FF00",
    "brown": "#A52A2A",
    "gold": "#FFD700",
    "indigo": "#4B0082",
    "violet": "#EE82EE",
    "coral": "#FF7F50",
    "crimson": "#DC143C",
    "transparent": "transparent",
}

BOOL_FLAGS: dict[str, str] = {
    "b": "bold",
    "bold": "bold",
    "i": "italic",
    "italic": "italic",
    "_": "underline",
    "underline": "underline",
    "-": "strike",
    "strike": "strike",
    "#": "code",
    "code": "code",
    "^": "sup",
    "sup": "sup",
    ",": "sub",
    "sub": "sub",
    "w": "small_caps",
    "smallcaps": "small_caps",
}

VALUE_KEYS = (
    "t=", "text=", "c=", "color=", "z=", "bg=", "f=", "font=", "s=", "size=",
    "u=", "url=", "h=", "heading=", "l=", "leading=", "a=", "align=", "o=", "opacity=",
    "n=", "indent=", "k=", "kerning=", "x=", "width=", "y=", "height=", "p=", "spacing=",
    "e=", "effect=", "cols=", "check=", "toc=", "img=", "T=", "@=", '"=',
    "layout=", "zone=", "shape=", "fill=", "stroke=", "notes=", "transition=", "move=",
)

BARE_KEYWORDS = {"0", "!0", "+", "check", "toc", "dup", "hide", "f", "s", "c", "z", "h", "p", "t"}


def resolve_color(value: str) -> str:
    lower = value.strip().lower()
    if lower in NAMED_COLORS:
        return NAMED_COLORS[lower]
    if re.fullmatch(r"#[0-9a-f]{3}", lower):
        h = lower[1:].upper()
        return f"#{h[0]*2}{h[1]*2}{h[2]*2}"
    if re.fullmatch(r"#[0-9a-f]{6}", lower):
        return lower.upper()
    return value


def _unquote(s: str) -> str:
    if len(s) >= 2 and ((s[0] == '"' and s[-1] == '"') or (s[0] == "'" and s[-1] == "'")):
        return s[1:-1]
    return s


def tokenize_brace_content(s: str) -> list[str]:
    tokens: list[str] = []
    cur: list[str] = []
    in_quote = False
    quote_char = ""
    for ch in s:
        if in_quote:
            cur.append(ch)
            if ch == quote_char:
                in_quote = False
        elif ch in ('"', "'"):
            in_quote = True
            quote_char = ch
            cur.append(ch)
        elif ch in (" ", "\t"):
            if cur:
                tokens.append("".join(cur))
                cur.clear()
        else:
            cur.append(ch)
    if cur:
        tokens.append("".join(cur))
    return tokens


def parse_brace_expression(raw: str) -> BraceExpression:
    s = raw.strip()
    expr = BraceExpression()
    if not s:
        return expr

    c_idx = s.find('"=' )
    if c_idx >= 0:
        expr.comment = _unquote(s[c_idx + 2:].strip())
        s = s[:c_idx].strip()

    if s == "0" or s.startswith("0 ") or s.startswith("0\t"):
        expr.reset = True
        s = s[1:].strip()

    for tok in tokenize_brace_content(s):
        if tok == "+" or tok.startswith("+="):
            expr.has_break = True
            expr.break_kind = tok[2:] if tok.startswith("+=") else ""
            continue
        if tok.startswith("@="):
            expr.bookmark = _unquote(tok[2:])
            continue
        if tok == "0":
            expr.reset = True
            continue
        if tok == "!0":
            expr.no_reset = True
            continue
        if tok.startswith("!"):
            flag = tok[1:]
            canon = BOOL_FLAGS.get(flag)
            if not canon:
                raise SedmatError(f"unknown negated flag: {flag}")
            setattr(expr, canon, False)
            continue
        if "=" in tok:
            key, raw_val = tok.split("=", 1)
            val = _unquote(raw_val)
            if key in BOOL_FLAGS:
                expr.inline_spans.append(InlineSpan(flag=BOOL_FLAGS[key], text=val))
                continue
            _parse_kv(key, val, expr)
            continue
        if tok in BOOL_FLAGS:
            setattr(expr, BOOL_FLAGS[tok], True)
            continue
        if tok == "check":
            expr.check = False
        elif tok == "toc":
            expr.has_toc = True
            expr.toc = -1
        elif tok == "h":
            expr.heading = "1"
        elif tok == "p":
            expr.spacing_set = True
            expr.spacing_above = 0.0
            expr.spacing_below = 0.0
        elif tok == "dup":
            expr.dup = True
        elif tok == "hide":
            expr.hide = True
        elif tok in ("t", "f", "s", "c", "z"):
            pass
        else:
            raise SedmatError(f"unknown brace flag: {tok}")

    return expr


def _parse_kv(key: str, val: str, expr: BraceExpression) -> None:
    if key in ("t", "text"):
        expr.text = val
    elif key in ("c", "color"):
        expr.color = resolve_color(val)
    elif key in ("z", "bg"):
        expr.bg = resolve_color(val)
    elif key in ("f", "font"):
        expr.font = val
    elif key in ("s", "size"):
        expr.size = float(val)
    elif key in ("u", "url"):
        expr.url = val
    elif key in ("h", "heading"):
        expr.heading = val
    elif key in ("l", "leading"):
        expr.leading = float(val)
    elif key in ("a", "align"):
        expr.align = val
    elif key in ("o", "opacity"):
        expr.opacity = float(val)
    elif key in ("n", "indent"):
        expr.indent = int(val)
    elif key in ("k", "kerning"):
        expr.kerning = float(val)
    elif key in ("x", "width"):
        expr.width = float(val)
    elif key in ("y", "height"):
        expr.height = float(val)
    elif key in ("p", "spacing"):
        expr.spacing_set = True
        parts = val.split(",", 1)
        expr.spacing_above = float(parts[0])
        expr.spacing_below = float(parts[1] if len(parts) > 1 else parts[0])
    elif key in ("e", "effect"):
        expr.effect = val
    elif key == "cols":
        expr.cols = int(val)
    elif key == "check":
        expr.check = val in ("y", "true", "1")
    elif key == "toc":
        expr.has_toc = True
        expr.toc = int(val)
    elif key == "img":
        expr.img_ref = val
    elif key == "T":
        expr.table_ref = val
    elif key == "layout":
        expr.layout = val
    elif key == "zone":
        expr.zone = val
    elif key == "shape":
        expr.shape = val
    elif key == "fill":
        expr.fill = resolve_color(val)
    elif key == "stroke":
        expr.stroke = resolve_color(val)
    elif key == "notes":
        expr.notes = val
    elif key == "transition":
        expr.transition = val
    elif key == "move":
        expr.move = int(val)
    else:
        raise SedmatError(f"unknown brace key: {key}")


def find_matching_brace(s: str, open_idx: int) -> int:
    if s[open_idx:open_idx + 3] == '{"=':
        return s.find("}", open_idx + 3)
    depth = 0
    in_quote = False
    quote_char = ""
    for i in range(open_idx, len(s)):
        ch = s[i]
        if in_quote:
            if ch == quote_char:
                in_quote = False
            continue
        if ch in ('"', "'"):
            in_quote = True
            quote_char = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
    return -1


def looks_like_brace_expression(content: str) -> bool:
    trimmed = content.strip()
    if not trimmed:
        return False
    first = trimmed.split()[0]
    if first in BARE_KEYWORDS or first in BOOL_FLAGS:
        return True
    if first.startswith("!") and first[1:] in BOOL_FLAGS:
        return True
    if trimmed.startswith(("+=", '"=', "@=")):
        return True
    if any(k in trimmed for k in VALUE_KEYS):
        return True
    return any(trimmed.startswith(f"{flag}=") for flag in BOOL_FLAGS)


def brace_expression_has_any_format(expr: BraceExpression | None) -> bool:
    if expr is None:
        return False
    return any([
        expr.bold is not None, expr.italic is not None, expr.underline is not None,
        expr.strike is not None, expr.code is not None, expr.sup is not None,
        expr.sub is not None, expr.small_caps is not None, bool(expr.inline_spans),
        bool(expr.text), bool(expr.color), bool(expr.bg), bool(expr.font),
        expr.size is not None, bool(expr.url), bool(expr.heading),
        expr.leading is not None, bool(expr.align), expr.opacity is not None,
        expr.indent is not None, expr.kerning is not None, expr.width is not None,
        expr.height is not None, expr.spacing_set, bool(expr.effect),
        expr.cols is not None, expr.reset, expr.no_reset, expr.has_break,
        bool(expr.comment), bool(expr.bookmark), expr.check is not None,
        expr.has_toc, bool(expr.img_ref), bool(expr.table_ref),
        bool(expr.layout), bool(expr.zone), bool(expr.shape), bool(expr.fill),
        bool(expr.stroke), bool(expr.notes), bool(expr.transition),
        expr.move is not None, expr.dup, expr.hide,
    ])


def has_brace_formatting(replacement: str) -> bool:
    i = 0
    while i < len(replacement):
        if replacement[i] == "\\" and i + 1 < len(replacement):
            i += 2
            continue
        if replacement[i] == "{" and (i == 0 or replacement[i - 1] != "$"):
            close = find_matching_brace(replacement, i)
            if close > i and looks_like_brace_expression(replacement[i + 1:close]):
                return True
        i += 1
    return False


def parse_brace_replacement(replacement: str) -> tuple[str, list[BraceSpan]]:
    if "{" not in replacement:
        return replacement, []
    spans: list[BraceSpan] = []
    cleaned: list[str] = []
    cleaned_len = 0
    i = 0
    while i < len(replacement):
        if replacement[i] == "\\" and i + 1 < len(replacement) and replacement[i + 1] in ("{", "}"):
            cleaned.append(replacement[i + 1])
            cleaned_len += 1
            i += 2
            continue
        if replacement[i] == "{" and (i == 0 or replacement[i - 1] != "$"):
            close = find_matching_brace(replacement, i)
            if close > i:
                inner = replacement[i + 1:close]
                if looks_like_brace_expression(inner):
                    try:
                        parsed = parse_brace_expression(inner)
                        if brace_expression_has_any_format(parsed):
                            raw = replacement[i:close + 1]
                            if parsed.inline_spans:
                                for inline in parsed.inline_spans:
                                    start = cleaned_len
                                    cleaned.append(inline.text)
                                    cleaned_len += len(inline.text)
                                    span_expr = copy.deepcopy(parsed)
                                    span_expr.inline_spans.clear()
                                    setattr(span_expr, inline.flag, True)
                                    spans.append(BraceSpan(start, cleaned_len, False, span_expr, raw))
                            else:
                                start = cleaned_len
                                if parsed.text:
                                    cleaned.append(parsed.text)
                                    cleaned_len += len(parsed.text)
                                is_global = i == 0 or close == len(replacement) - 1
                                spans.append(BraceSpan(start, cleaned_len, is_global, parsed, raw))
                            i = close + 1
                            continue
                    except SedmatError:
                        pass
        cleaned.append(replacement[i])
        cleaned_len += 1
        i += 1
    return "".join(cleaned), spans


def merge_brace_spans(spans: list[BraceSpan]) -> BraceExpression:
    merged = BraceExpression()
    for span in spans:
        if not span.is_global:
            continue
        s = span.expr
        for attr in (
            "bold", "italic", "underline", "strike", "code", "sup", "sub", "small_caps",
            "color", "bg", "font", "size", "url", "heading", "align", "leading", "indent",
            "cols", "check", "comment", "bookmark", "img_ref", "table_ref",
        ):
            val = getattr(s, attr)
            if val is not None:
                setattr(merged, attr, val)
        if s.has_toc:
            merged.has_toc = True
            merged.toc = s.toc
        if s.reset:
            merged.reset = True
        if s.no_reset:
            merged.no_reset = True
        if s.has_break:
            merged.has_break = True
            merged.break_kind = s.break_kind
    return merged
