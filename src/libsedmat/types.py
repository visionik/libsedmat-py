from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


class SedmatError(ValueError):
    """Raised on SEDMAT syntax, address, or execution errors."""


@dataclass
class Address:
    start: int  # 1-based, or -1 for '$'
    end: int = 0  # 1-based, -1 for '$', or 0 for single address
    has_range: bool = False


@dataclass
class ContainerScope:
    container_type: str | None = None
    address: Address | None = None
    all: bool = False
    name: str | None = None
    region: str | None = None
    container_op: bool = False


@dataclass
class InlineSpan:
    flag: str
    text: str


@dataclass
class BraceExpression:
    bold: bool | None = None
    italic: bool | None = None
    underline: bool | None = None
    strike: bool | None = None
    code: bool | None = None
    sup: bool | None = None
    sub: bool | None = None
    small_caps: bool | None = None

    text: str | None = None
    color: str | None = None
    bg: str | None = None
    font: str | None = None
    size: float | None = None
    url: str | None = None
    heading: str | None = None
    leading: float | None = None
    align: str | None = None
    opacity: float | None = None
    indent: int | None = None
    kerning: float | None = None
    width: float | None = None
    height: float | None = None
    spacing_set: bool = False
    spacing_above: float = 0.0
    spacing_below: float = 0.0
    effect: str | None = None
    cols: int | None = None

    reset: bool = False
    no_reset: bool = False
    has_break: bool = False
    break_kind: str = ""
    comment: str | None = None
    bookmark: str | None = None
    check: bool | None = None
    has_toc: bool = False
    toc: int = 0
    img_ref: str | None = None
    table_ref: str | None = None

    # v3.7 slide & shape flags
    layout: str | None = None
    zone: str | None = None
    shape: str | None = None
    fill: str | None = None
    stroke: str | None = None
    notes: str | None = None
    transition: str | None = None
    move: int | None = None
    dup: bool = False
    hide: bool = False

    inline_spans: list[InlineSpan] = field(default_factory=list)


@dataclass
class BraceSpan:
    start: int
    end: int
    is_global: bool
    expr: BraceExpression
    raw: str = ""


@dataclass
class TableCreateSpec:
    rows: int
    columns: int
    header: bool = False
    cells: list[list[str]] = field(default_factory=list)


@dataclass
class Expression:
    command: str  # "s", "d", "a", "i", "y", "brace"
    pattern: str = ""
    replacement: str = ""
    global_flag: bool = False
    nth_match: int = 0
    flags: str = ""
    address: Address | None = None
    container: ContainerScope | None = None
    brace: BraceExpression | None = None
    brace_spans: list[BraceSpan] = field(default_factory=list)
    table_create: TableCreateSpec | None = None
    enriched: bool = False


@dataclass
class Program:
    expressions: list[Expression] = field(default_factory=list)


@dataclass
class DocumentBlock:
    kind: str  # "paragraph", "table", "table_of_contents", "section_break"
    start_index: int
    end_index: int
    item_index: int = -1


@dataclass
class DocumentParagraph:
    text: str
    start_index: int
    end_index: int
    named_style: str = "NORMAL_TEXT"
    bullet_list_id: str | None = None
    bullet_nesting_level: int = 0


@dataclass
class DocumentTableCell:
    text: str
    start_index: int
    end_index: int
    text_start_index: int
    text_end_index: int


@dataclass
class DocumentTableRow:
    cells: list[DocumentTableCell] = field(default_factory=list)


@dataclass
class DocumentTable:
    start_index: int
    end_index: int
    declared_rows: int = 0
    declared_columns: int = 0
    rows: list[DocumentTableRow] = field(default_factory=list)


@dataclass
class DocumentSegment:
    tab_id: str = ""
    title: str = ""
    body_start_index: int = 1
    body_end_index: int = 1
    blocks: list[DocumentBlock] = field(default_factory=list)
    paragraphs: list[DocumentParagraph] = field(default_factory=list)
    tables: list[DocumentTable] = field(default_factory=list)


@dataclass
class DocumentProjection:
    document_id: str = ""
    revision_id: str = ""
    legacy: DocumentSegment | None = None
    tabs: list[DocumentSegment] = field(default_factory=list)


@dataclass
class AddressElement:
    number: int
    kind: str  # "paragraph", "table", "toc"
    text: str
    start_index: int
    end_index: int


@dataclass
class AddressMutation:
    start_index: int
    end_index: int
    insert_text: str | None = None


@dataclass
class TextEdit:
    start_index: int
    end_index: int
    insert_text: str


@dataclass
class FormatIntent:
    start_index: int
    end_index: int
    formats: list[str] = field(default_factory=list)
    brace: BraceExpression | None = None


@dataclass
class TextPlan:
    match_count: int = 0
    text_edits: list[TextEdit] = field(default_factory=list)
    formatting: list[FormatIntent] = field(default_factory=list)


@dataclass
class ExecuteOptions:
    dry_run: bool = False
    tab_id: str = ""


@dataclass
class ExecutionReport:
    dry_run: bool = False
    total_matches: int = 0


class Backend(Protocol):
    def project(self) -> DocumentProjection: ...
    def apply_text_plan(self, tab_id: str, plan: TextPlan) -> None: ...
    def apply_address_mutations(self, tab_id: str, mutations: list[AddressMutation]) -> None: ...
    def apply_transliterate(
        self, tab_id: str, source: str, dest: str, targets: list[AddressElement]
    ) -> int: ...
    def apply_container_op(self, scope: ContainerScope, expr: Expression) -> int: ...
