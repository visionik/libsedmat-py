"""Context-aware IntelliSense / IntelliCode completion, live grammar signatures,
structured diagnostics, and lightweight syntax tokenization for SEDMAT v3.6 / v3.7.

UI-agnostic and zero-dependency: usable from web editor bars, TUIs, CLIs, and LSPs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional, Sequence

SuggestionKind = Literal["scope", "command", "flag", "value", "snippet"]
Profile = Literal["document", "word", "slides", "spreadsheet", "vector", "timeline", "all"]
TokenKind = Literal[
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


@dataclass
class Suggestion:
    label: str
    insert_text: str
    replace_from: int
    replace_to: int
    detail: str
    kind: SuggestionKind
    swatch: Optional[str] = None


@dataclass
class SignaturePart:
    text: str
    active: bool = False


@dataclass
class IntelliSenseResult:
    context_title: str
    signature: List[SignaturePart]
    suggestions: List[Suggestion]
    ghost_suffix: Optional[str] = None


@dataclass
class FlagDefinition:
    key: str
    insert: str
    detail: str
    profiles: Sequence[Profile] = ()


@dataclass
class ValueOption:
    value: str
    detail: str
    swatch: Optional[str] = None


@dataclass
class SnippetOption:
    label: str
    insert: str
    detail: str
    kind: SuggestionKind
    swatch: Optional[str] = None


@dataclass
class IntelliSenseExtensions:
    flags: List[FlagDefinition] = field(default_factory=list)
    values: Dict[str, List[ValueOption]] = field(default_factory=dict)
    starters: List[SnippetOption] = field(default_factory=list)
    scope_snippets: List[SnippetOption] = field(default_factory=list)


@dataclass
class ContextInfo:
    mode: Profile = "document"
    active_container: Optional[int] = None
    total_containers: Optional[int] = None
    active_slide: Optional[int] = None
    total_slides: Optional[int] = None
    extensions: Optional[IntelliSenseExtensions] = None


@dataclass
class Diagnostic:
    ok: bool
    summary: str
    error_offset: Optional[int] = None
    error_length: int = 0
    hint: Optional[str] = None


@dataclass
class Token:
    kind: TokenKind
    start: int
    end: int
    text: str


_OFFSET_RE = re.compile(r"at offset (\d+):\s*(.+)$", re.IGNORECASE)
_SUB_CMD_RE = re.compile(r"(?:^|:|\d|\$|\s)s/")
_REGION_RE = re.compile(
    r"^(?:title|subtitle|sub|body|notes|header|footer|shape=[1-9]\d*):",
    re.IGNORECASE,
)


def extract_diagnostic(err: object) -> Diagnostic:
    """Extract structured error offset, span length, clean reason, and hint from any SEDMAT error."""
    offset = getattr(err, "offset", None)
    length = getattr(err, "length", None)
    reason = getattr(err, "reason", None)
    hint = getattr(err, "hint", None)
    if isinstance(offset, int) or isinstance(reason, str):
        return Diagnostic(
            ok=False,
            summary=reason if isinstance(reason, str) else str(err),
            error_offset=offset if isinstance(offset, int) else None,
            error_length=max(1, length) if isinstance(length, int) else 1,
            hint=hint if isinstance(hint, str) else None,
        )

    msg = str(err)
    m = _OFFSET_RE.search(msg)
    if m:
        raw_rest = m.group(2)
        parts = raw_rest.split(" — ", 1)
        return Diagnostic(
            ok=False,
            summary=parts[0].strip(),
            error_offset=int(m.group(1)),
            error_length=1,
            hint=parts[1].strip() if len(parts) > 1 else None,
        )
    return Diagnostic(ok=False, summary=msg)


def _normalize_profile(mode: Optional[Profile]) -> str:
    if not mode or mode == "word":
        return "document"
    return mode


def _matches_profile(defn: FlagDefinition, profile: str) -> bool:
    if profile == "all" or not defn.profiles:
        return True
    return any(("document" if p == "word" else p) == profile for p in defn.profiles)


_FLAG_DEFS: List[FlagDefinition] = [
    # Timeline directives
    FlagDefinition("+2d", "+2d", "Extend task duration by +2 working days", ("timeline",)),
    FlagDefinition("-1d", "-1d", "Shorten task duration by -1 working day", ("timeline",)),
    FlagDefinition("5d", "5d", "Set exact task duration to 5 working days", ("timeline",)),
    FlagDefinition("+4h", "+4h", "Extend task duration by +4 working hours", ("timeline",)),
    FlagDefinition("50%", "50%", "Set task completion to 50%", ("timeline",)),
    FlagDefinition("100%", "100%", "Mark task 100% complete", ("timeline",)),
    FlagDefinition("milestone", "milestone", "Convert task into a 0-day milestone", ("timeline",)),
    # Core inline formatting
    FlagDefinition("b", "b", "Bold", ("document", "slides", "spreadsheet", "vector")),
    FlagDefinition("i", "i", "Italic", ("document", "slides", "spreadsheet", "vector")),
    FlagDefinition("_", "_", "Underline", ("document", "slides", "spreadsheet")),
    FlagDefinition("-", "-", "Strikethrough", ("document", "slides", "spreadsheet")),
    FlagDefinition("c=", "c=", "Text / foreground color (red, blue, #FF0000…)"),
    FlagDefinition("z=", "z=", "Background / highlight / fill color"),
    FlagDefinition("s=", "s=", "Font size in pt (e.g. s=14)", ("document", "slides", "spreadsheet", "vector")),
    FlagDefinition("f=", "f=", "Font family (e.g. f=Inter)", ("document", "slides", "spreadsheet", "vector")),
    FlagDefinition("a=", "a=", "Alignment (left, center, right, justify)", ("document", "slides", "spreadsheet", "vector")),
    FlagDefinition("t=", "t=", "Replacement text while styling match", ("document", "slides", "vector")),
    FlagDefinition("u=", "u=", "Hyperlink URL, #bookmark, or chip:// URI", ("document", "slides", "spreadsheet")),
    FlagDefinition("#", "#", "Inline monospace code", ("document", "slides")),
    FlagDefinition("w", "w", "Small caps", ("document", "slides")),
    FlagDefinition("^", "^", "Superscript", ("document", "slides")),
    FlagDefinition(",", ",", "Subscript", ("document", "slides")),
    FlagDefinition("!b", "!b", "Remove bold (negate any boolean flag with !)", ("document", "slides", "vector")),
    FlagDefinition("!0", "!0", "Additive mode (opt out of implicit reset)", ("document", "slides", "spreadsheet", "vector")),
    FlagDefinition("0", "0", "Reset all formatting", ("document", "slides", "spreadsheet", "vector")),
    # Slides, Vector & Shape flags (v3.7)
    FlagDefinition("shape=", "shape=", "Shape geometry (roundRect, rect, diamond, ellipse…)", ("slides", "vector")),
    FlagDefinition("fill=", "fill=", "Shape fill hex or named color", ("slides", "vector", "timeline")),
    FlagDefinition("stroke=", "stroke=", "Shape border hex or named color", ("slides", "vector")),
    FlagDefinition("layout=", "layout=", "Slide layout (title, content, two-col, section, blank)", ("slides",)),
    FlagDefinition("zone=", "zone=", "Placement zone (left, right, top, bottom, center, footer)", ("slides",)),
    FlagDefinition("transition=", "transition=", "Slide transition (fade, push, wipe, none)", ("slides",)),
    FlagDefinition("move=", "move=", "Move container to 1-based position (e.g. @3{move=1})", ("slides", "spreadsheet")),
    FlagDefinition("dup", "dup", "Duplicate container (e.g. @2{dup})", ("slides", "vector", "spreadsheet")),
    FlagDefinition("hide", "hide", "Hide container", ("slides", "spreadsheet")),
    # Document-specific structural flags
    FlagDefinition("h=", "h=", "Heading level (t=Title, s=Subtitle, 1..6, 0=Normal)", ("document",)),
    FlagDefinition("p=", "p=", "Paragraph spacing before,after pt (e.g. p=12,6)", ("document",)),
    FlagDefinition("n=", "n=", "Paragraph left indent level", ("document",)),
    FlagDefinition("cols=", "cols=", "Section columns (e.g. cols=2)", ("document",)),
    FlagDefinition('"=', '"=', 'Attach review comment (e.g. "=Check figure)', ("document",)),
    FlagDefinition("@=", "@=", "Insert bookmark anchor (e.g. @=summary)", ("document",)),
    FlagDefinition("check", "check", "Insert checkbox (check or check=y)", ("document",)),
    FlagDefinition("toc", "toc", "Insert Table of Contents", ("document",)),
    FlagDefinition("+=p", "+=p", "Insert page break (+, +=p, +=c, +=s)", ("document",)),
    # Tables & images
    FlagDefinition("T=", "T=", "Table create/cell ref (T=3x4:header or T=1!A1)", ("document", "slides")),
    FlagDefinition("img=", "img=", "Target image by 1-based index (img=1, img=-1)", ("document", "slides")),
    FlagDefinition("x=", "x=", "Image width in px (e.g. x=420)", ("document", "slides")),
]

# Canonical sedmat.org 18-color palette swatches
_COLOR_VALUES: List[ValueOption] = [
    ValueOption("red", "Canonical red", "#FF0000"),
    ValueOption("blue", "Canonical blue", "#0000FF"),
    ValueOption("green", "Canonical green", "#00FF00"),
    ValueOption("orange", "Canonical orange", "#FF8C00"),
    ValueOption("purple", "Canonical purple", "#800080"),
    ValueOption("navy", "Canonical navy", "#000080"),
    ValueOption("teal", "Canonical teal", "#008080"),
    ValueOption("gray", "Canonical gray", "#808080"),
    ValueOption("yellow", "Highlight yellow", "#FFFF00"),
    ValueOption("black", "Canonical black", "#000000"),
    ValueOption("white", "Canonical white", "#FFFFFF"),
]

_VALUE_COMPLETIONS: Dict[str, List[ValueOption]] = {
    "c": _COLOR_VALUES,
    "z": _COLOR_VALUES,
    "fill": _COLOR_VALUES,
    "stroke": _COLOR_VALUES,
    "a": [
        ValueOption("left", "Align left"),
        ValueOption("center", "Align center"),
        ValueOption("right", "Align right"),
        ValueOption("justify", "Justify paragraph"),
    ],
    "h": [
        ValueOption("t", "Document Title"),
        ValueOption("s", "Subtitle"),
        ValueOption("1", "Heading 1"),
        ValueOption("2", "Heading 2"),
        ValueOption("3", "Heading 3"),
        ValueOption("0", "Normal paragraph"),
    ],
    "layout": [
        ValueOption("content", "Title + bullet body"),
        ValueOption("title", "Centered cover title"),
        ValueOption("two-col", "Two-column comparison"),
        ValueOption("section", "Section divider header"),
        ValueOption("comparison", "Side-by-side comparison"),
        ValueOption("blank", "Blank canvas"),
    ],
    "zone": [
        ValueOption("center", "Center stage"),
        ValueOption("left", "Left column"),
        ValueOption("right", "Right column"),
        ValueOption("top", "Upper band"),
        ValueOption("bottom", "Lower band"),
        ValueOption("footer", "Bottom footer"),
    ],
    "shape": [
        ValueOption("roundRect", "Rounded rectangle"),
        ValueOption("rect", "Rectangle"),
        ValueOption("ellipse", "Circle / oval"),
        ValueOption("diamond", "Decision diamond"),
        ValueOption("rightArrow", "Right arrow"),
        ValueOption("chevron", "Process chevron"),
    ],
    "transition": [
        ValueOption("fade", "Smooth crossfade"),
        ValueOption("push", "Slide push"),
        ValueOption("wipe", "Directional wipe"),
        ValueOption("none", "No transition"),
    ],
    "f": [
        ValueOption("Arial", "Classic sans-serif"),
        ValueOption("Calibri", "Office sans-serif"),
        ValueOption("Georgia", "Editorial serif"),
        ValueOption("Inter", "Modern UI sans"),
        ValueOption("Consolas", "Monospace code"),
    ],
    "s": [
        ValueOption("11", "11 pt default"),
        ValueOption("12", "12 pt body"),
        ValueOption("16", "16 pt lead"),
        ValueOption("24", "24 pt heading"),
        ValueOption("36", "36 pt title"),
    ],
}


def _find_open_brace(before: str) -> int:
    depth = 0
    last_open = -1
    i = 0
    n = len(before)
    while i < n:
        ch = before[i]
        if ch == "\\" and i + 1 < n:
            i += 2
            continue
        if ch == "{":
            depth += 1
            last_open = i
        elif ch == "}":
            depth = max(0, depth - 1)
            if depth == 0:
                last_open = -1
        i += 1
    return last_open if depth > 0 else -1


def _count_unescaped_slashes(text: str) -> int:
    count = 0
    i = 0
    n = len(text)
    while i < n:
        if text[i] == "\\" and i + 1 < n:
            i += 2
            continue
        if text[i] == "/":
            count += 1
        i += 1
    return count


def _compute_ghost_suffix(
    text: str,
    cursor: int,
    suggestions: List[Suggestion],
) -> Optional[str]:
    if cursor != len(text) or not suggestions:
        return None
    top = suggestions[0]
    typed = text[top.replace_from : top.replace_to]
    if len(top.insert_text) > len(typed) and top.insert_text.lower().startswith(typed.lower()):
        return top.insert_text[len(typed) :]
    return None


def get_completions(
    text: str,
    cursor: int,
    ctx: Optional[ContextInfo] = None,
) -> IntelliSenseResult:
    """Produce live IntelliSense suggestions, grammar parameter hints, and ghost completion."""
    info = ctx or ContextInfo()
    profile = _normalize_profile(info.mode)
    safe_cursor = max(0, min(len(text), cursor))
    before = text[:safe_cursor]
    container_num = (
        info.active_container
        if info.active_container is not None
        else (info.active_slide if info.active_slide is not None else 1)
    )

    last_semi = before.rfind(";")
    seg_start = last_semi + 1 if last_semi >= 0 else 0
    raw_seg = before[seg_start:]
    leading_spaces = len(raw_seg) - len(raw_seg.lstrip())
    cmd_start = seg_start + leading_spaces
    seg = before[cmd_start:]

    # 1. Inside `{...}` formatting / operation braces
    brace_idx = _find_open_brace(before)
    if brace_idx >= cmd_start:
        inside = before[brace_idx + 1 :]
        last_space = max(inside.rfind(" "), inside.rfind("\t"))
        token_start = brace_idx + 1 + last_space + 1
        token = before[token_start:]

        eq_idx = token.find("=")
        if eq_idx > 0:
            key = token[:eq_idx]
            val_typed = token[eq_idx + 1 :].lower()
            val_start = token_start + eq_idx + 1
            value_list = (
                info.extensions.values.get(key)
                if info.extensions and key in info.extensions.values
                else _VALUE_COMPLETIONS.get(key)
            )
            if value_list is not None:
                filtered = [
                    Suggestion(
                        label=v.value,
                        insert_text=v.value,
                        replace_from=val_start,
                        replace_to=safe_cursor,
                        detail=v.detail,
                        kind="value",
                        swatch=v.swatch,
                    )
                    for v in value_list
                    if not val_typed
                    or val_typed in v.value.lower()
                    or val_typed in v.detail.lower()
                ]
                return IntelliSenseResult(
                    context_title=f"Value for {{{key}=…}}",
                    signature=[
                        SignaturePart("{ "),
                        SignaturePart(f"{key}="),
                        SignaturePart("value", active=True),
                        SignaturePart(" }"),
                    ],
                    suggestions=filtered,
                    ghost_suffix=_compute_ghost_suffix(text, safe_cursor, filtered),
                )

        q = token.lower()
        all_flags = list(info.extensions.flags if info.extensions else []) + _FLAG_DEFS
        relevant = [
            f
            for f in all_flags
            if _matches_profile(f, profile)
            and (not q or f.key.lower().startswith(q) or q in f.detail.lower())
        ][:12]
        suggestions = [
            Suggestion(
                label=f.key,
                insert_text=f.insert,
                replace_from=token_start,
                replace_to=safe_cursor,
                detail=f.detail,
                kind="flag",
            )
            for f in relevant
        ]
        return IntelliSenseResult(
            context_title="SEDMAT Brace Flags ({…})",
            signature=[
                SignaturePart("{"),
                SignaturePart("b i _ - c= z= s= f= a= !0 …", active=True),
                SignaturePart("}"),
            ],
            suggestions=suggestions,
            ghost_suffix=_compute_ghost_suffix(text, safe_cursor, suggestions),
        )

    # 2. Typing a `@` container scope prefix
    if seg.startswith("@"):
        first_colon = seg.find(":")
        if first_colon == -1:
            q = seg.lower()
            if profile == "slides":
                base_scopes = [
                    SnippetOption(f"@{container_num}:", f"@{container_num}:", f"Target slide {container_num}", "scope"),
                    SnippetOption(f"@{container_num}:title:", f"@{container_num}:title:", f"Target slide {container_num} title", "scope"),
                    SnippetOption(f"@{container_num}:body:", f"@{container_num}:body:", f"Target slide {container_num} body", "scope"),
                    SnippetOption(f"@{container_num}:notes:", f"@{container_num}:notes:", f"Target slide {container_num} speaker notes", "scope"),
                    SnippetOption("@*:", "@*:", "Target ALL slides", "scope"),
                    SnippetOption(f"@{container_num}:{{z=#0F172A}}", f"@{container_num}:{{z=#0F172A}}", "Set slide background", "snippet"),
                    SnippetOption("@$a/{layout=two-col}New Slide/", "@$a/{layout=two-col}New Slide/", "Append new slide", "snippet"),
                    SnippetOption(f"@{container_num}{{dup}}", f"@{container_num}{{dup}}", f"Duplicate slide {container_num}", "command"),
                    SnippetOption(f"@{container_num}{{move=1}}", f"@{container_num}{{move=1}}", f"Move slide {container_num} to position 1", "command"),
                    SnippetOption(f"@{container_num}d", f"@{container_num}d", f"Delete slide {container_num}", "command"),
                ]
            elif profile == "spreadsheet":
                base_scopes = [
                    SnippetOption(f"@{container_num}:", f"@{container_num}:", f"Target sheet {container_num}", "scope"),
                    SnippetOption("@sheet=", "@sheet=", "Target named worksheet", "scope"),
                    SnippetOption("@*:", "@*:", "Target ALL sheets", "scope"),
                ]
            else:
                base_scopes = [
                    SnippetOption("@header:", "@header:", "Target document header", "scope"),
                    SnippetOption("@footer:", "@footer:", "Target document footer", "scope"),
                    SnippetOption(f"@{container_num}:", f"@{container_num}:", f"Target container {container_num}", "scope"),
                    SnippetOption("@*:", "@*:", "Target all containers", "scope"),
                ]

            scope_snippets = list(info.extensions.scope_snippets if info.extensions else []) + base_scopes
            filtered = [
                Suggestion(
                    label=s.label,
                    insert_text=s.insert,
                    replace_from=cmd_start,
                    replace_to=safe_cursor,
                    detail=s.detail,
                    kind=s.kind,
                    swatch=s.swatch,
                )
                for s in scope_snippets
                if q in s.label.lower() or q in s.detail.lower()
            ]
            return IntelliSenseResult(
                context_title="Container Scope (@)",
                signature=[
                    SignaturePart("@container", active=True),
                    SignaturePart("[:region]:command"),
                ],
                suggestions=filtered,
                ghost_suffix=_compute_ghost_suffix(text, safe_cursor, filtered),
            )

        after_first = seg[first_colon + 1 :]
        if ":" not in after_first and "/" not in after_first and not after_first.startswith("{"):
            token_start = cmd_start + first_colon + 1
            q = after_first.lower()
            if profile == "slides":
                post_scope = [
                    SnippetOption("title:", "title:", "Slide title placeholder", "scope"),
                    SnippetOption("sub:", "sub:", "Slide subtitle placeholder", "scope"),
                    SnippetOption("body:", "body:", "Slide body / bullets", "scope"),
                    SnippetOption("notes:", "notes:", "Speaker notes", "scope"),
                    SnippetOption("s/old/new/g", "s/", "Search & replace text or style", "command"),
                    SnippetOption("a/text/", "a/", "Append bullet / paragraph", "command"),
                    SnippetOption("d/pattern/", "d/", "Delete matching lines", "command"),
                    SnippetOption("{z=#0F172A}", "{z=", "Set slide background color", "flag"),
                    SnippetOption("{transition=fade}", "{transition=", "Set slide transition", "flag"),
                ]
            else:
                post_scope = [
                    SnippetOption("s/old/new/g", "s/", "Search & replace in container", "command"),
                    SnippetOption("a/text/", "a/", "Append paragraph", "command"),
                    SnippetOption("d/pattern/", "d/", "Delete matching paragraphs", "command"),
                ]
            filtered = [
                Suggestion(
                    label=item.label,
                    insert_text=item.insert,
                    replace_from=token_start,
                    replace_to=safe_cursor,
                    detail=item.detail,
                    kind=item.kind,
                    swatch=item.swatch,
                )
                for item in post_scope
                if not q or item.label.lower().startswith(q) or q in item.detail.lower()
            ]
            prefix = seg[: first_colon + 1]
            return IntelliSenseResult(
                context_title=f"Inside {prefix}",
                signature=[
                    SignaturePart(prefix),
                    SignaturePart("region: | command | {flags}", active=True),
                ],
                suggestions=filtered,
                ghost_suffix=_compute_ghost_suffix(text, safe_cursor, filtered),
            )

    # 3. Inside an active `s/.../.../...` substitution command
    sub_match = _SUB_CMD_RE.search(seg)
    if sub_match:
        after_s = seg[sub_match.end() :]
        slashes = _count_unescaped_slashes(after_s)
        if slashes == 0:
            return IntelliSenseResult(
                context_title="Substitution — Pattern (RegExp)",
                signature=[
                    SignaturePart("s/"),
                    SignaturePart("pattern", active=True),
                    SignaturePart("/replacement/[g i m N]"),
                ],
                suggestions=[
                    Suggestion(
                        label=".*/{b}/",
                        insert_text=".*/{b}/",
                        replace_from=safe_cursor,
                        replace_to=safe_cursor,
                        detail="Match entire element and apply formatting",
                        kind="snippet",
                    )
                ],
            )
        if slashes == 1:
            return IntelliSenseResult(
                context_title="Substitution — Replacement (type { for formatting flags)",
                signature=[
                    SignaturePart("s/pattern/"),
                    SignaturePart("{flags}replacement", active=True),
                    SignaturePart("/[g i m N]"),
                ],
                suggestions=[
                    Suggestion("{b c=red}", "{b c=red}", safe_cursor, safe_cursor, "Bold red highlight (keeps matched text)", "snippet", "#FF0000"),
                    Suggestion("{b}", "{b}", safe_cursor, safe_cursor, "Make match bold", "flag"),
                    Suggestion("{z=yellow}", "{z=yellow}", safe_cursor, safe_cursor, "Highlight match yellow", "flag", "#FFFF00"),
                    Suggestion("{!0 b c=blue}", "{!0 b c=blue}", safe_cursor, safe_cursor, "Add bold blue without resetting existing style", "snippet", "#0000FF"),
                    Suggestion("$0", "$0", safe_cursor, safe_cursor, "Insert original matched text", "value"),
                ],
            )

        trailing = after_s[after_s.rfind("/") + 1 :]
        opts = [
            ("g", "Global — replace every match"),
            ("i", "Case-insensitive regex match"),
            ("m", "Multiline ^ and $ anchors"),
            ("2", "Replace only the 2nd match"),
        ]
        trailing_opts = [
            Suggestion(flag, flag, safe_cursor, safe_cursor, detail, "flag")
            for flag, detail in opts
            if flag not in trailing
        ]
        return IntelliSenseResult(
            context_title="Substitution — Trailing Flags",
            signature=[
                SignaturePart("s/pattern/replacement/"),
                SignaturePart("[g i m N]", active=True),
            ],
            suggestions=trailing_opts,
            ghost_suffix=_compute_ghost_suffix(text, safe_cursor, trailing_opts),
        )

    # 4. Default / Start of expression
    q = seg.lower()
    if profile == "slides":
        base_starters = [
            SnippetOption(f"@{container_num}:title:s/.*/New Title/", f"@{container_num}:title:s/.*/", f"Edit slide {container_num} title", "snippet"),
            SnippetOption("s/old/{b c=blue t=new}/g", "s/", f"Search & replace on slide {container_num}", "command"),
            SnippetOption("@*:s/old/new/gi", "@*:s/", "Search & replace across ALL slides", "snippet"),
            SnippetOption(f"@{container_num}:notes:a/Talking point/", f"@{container_num}:notes:a/", f"Append speaker note on slide {container_num}", "snippet"),
            SnippetOption("@$a/{layout=two-col}New Slide/", "@$a/{layout=two-col}", "Append a new slide", "snippet"),
        ]
    else:
        base_starters = [
            SnippetOption("s/old/new/g", "s/", "Search & replace across document", "command"),
            SnippetOption("s/TODO/{b c=red}/g", "s/TODO/{b c=red}/g", "Highlight every TODO in bold red", "snippet"),
            SnippetOption("1s/.*/{h=t}/", "1s/.*/{h=t}/", "Format element 1 as Title", "snippet"),
            SnippetOption("$a/{h=2}Next Steps/", "$a/{h=2}", "Append a new Heading 2 at end", "snippet"),
            SnippetOption("d/DRAFT/i", "d/", "Delete elements matching pattern", "command"),
            SnippetOption("s/{T=1!A1}/{b}Header/", "s/{T=1!A1}/", "Edit cell A1 of table 1", "snippet"),
            SnippetOption("@header:s/.*/CONFIDENTIAL/", "@header:s/", "Edit document header", "scope"),
        ]

    starters = list(info.extensions.starters if info.extensions else []) + base_starters
    filtered = [
        Suggestion(
            label=s.label,
            insert_text=s.insert,
            replace_from=cmd_start,
            replace_to=safe_cursor,
            detail=s.detail,
            kind=s.kind,
            swatch=s.swatch,
        )
        for s in starters
        if not q or q in s.label.lower() or q in s.detail.lower()
    ]
    return IntelliSenseResult(
        context_title="SEDMAT v3.7",
        signature=[
            SignaturePart("[@scope:][addr]", active=not seg),
            SignaturePart("cmd/pattern/{flags}replacement/[g i m N]"),
        ],
        suggestions=filtered,
        ghost_suffix=_compute_ghost_suffix(text, safe_cursor, filtered),
    )


def tokenize_sedmat(text: str) -> List[Token]:
    """Lightweight, non-throwing syntax tokenizer for SEDMAT expressions."""
    tokens: List[Token] = []
    i = 0
    n = len(text)

    def push(kind: TokenKind, start: int, end: int) -> None:
        if end > start:
            tokens.append(Token(kind=kind, start=start, end=end, text=text[start:end]))

    while i < n:
        ch = text[i]
        if ch.isspace():
            s = i
            while i < n and text[i].isspace():
                i += 1
            push("whitespace", s, i)
            continue
        if ch == ";":
            push("delimiter", i, i + 1)
            i += 1
            continue
        if ch == "#":
            s = i
            nl = text.find("\n", i)
            i = nl if nl >= 0 else n
            push("comment", s, i)
            continue
        if ch == "@":
            s = i
            i += 1
            while i < n and not text[i].isspace() and text[i] not in ";{/":
                if text[i] == '"':
                    i += 1
                    while i < n and text[i] != '"':
                        i += 1
                    if i < n:
                        i += 1
                    continue
                if text[i] == ":":
                    i += 1
                    m = _REGION_RE.match(text[i:])
                    if m:
                        i += m.end()
                    break
                if text[i] in "dai" and (i + 1 >= n or text[i + 1].isspace() or text[i + 1] in ";/"):
                    break
                i += 1
            push("scope", s, i)
            continue
        if ch == "$" or ch.isdigit():
            s = i
            while i < n and (text[i].isdigit() or text[i] in ",$!"):
                i += 1
            push("address", s, i)
            continue
        if ch == "{":
            s = i
            depth = 0
            while i < n:
                if text[i] == "\\" and i + 1 < n:
                    i += 2
                    continue
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    i += 1
                    if depth == 0:
                        break
                    continue
                i += 1
            push("brace", s, i)
            continue
        if ch in "sdaciy":
            cmd = ch
            push("command", i, i + 1)
            i += 1
            if i < n and not text[i].isspace() and text[i] != ";":
                delim = text[i]
                push("delimiter", i, i + 1)
                i += 1
                expected_parts = 2 if cmd in ("s", "y") else 1
                for part in range(expected_parts):
                    if i >= n:
                        break
                    p_start = i
                    while i < n and text[i] != "\n":
                        if text[i] == "\\" and i + 1 < n:
                            i += 2
                            continue
                        if text[i] == delim:
                            break
                        if part == 1 and text[i] == "{":
                            push("text", p_start, i)
                            b_start = i
                            depth = 0
                            while i < n and text[i] != "\n":
                                if text[i] == "\\" and i + 1 < n:
                                    i += 2
                                    continue
                                if text[i] == "{":
                                    depth += 1
                                elif text[i] == "}":
                                    depth -= 1
                                    i += 1
                                    if depth == 0:
                                        break
                                    continue
                                i += 1
                            push("brace", b_start, i)
                            p_start = i
                            continue
                        i += 1
                    if i > p_start:
                        push("pattern" if part == 0 else "text", p_start, i)
                    if i < n and text[i] == delim:
                        push("delimiter", i, i + 1)
                        i += 1
                f_start = i
                while i < n and (text[i] in "gim" or text[i].isdigit()):
                    i += 1
                push("flag", f_start, i)
            continue

        push("text", i, i + 1)
        i += 1

    return tokens
