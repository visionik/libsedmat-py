from __future__ import annotations

from dataclasses import dataclass, field

from .parser import enrich, parse_program
from .planner import (
    address_elements,
    compile_sed_regex,
    plan_addressed_append,
    plan_addressed_delete,
    plan_addressed_insert,
    plan_paragraph_substitutions,
    resolve_address,
    select_segment,
    utf16_len,
)
from .types import (
    AddressElement,
    AddressMutation,
    Backend,
    ContainerScope,
    DocumentBlock,
    DocumentParagraph,
    DocumentProjection,
    DocumentSegment,
    ExecuteOptions,
    ExecutionReport,
    Expression,
    FormatIntent,
    Program,
    SedmatError,
    TextPlan,
)


@dataclass
class MemoryParagraph:
    text: str
    named_style: str = "NORMAL_TEXT"


@dataclass
class MemoryTab:
    id: str = ""
    title: str = "Default"
    background: str | None = None
    notes: str | None = None
    transition: str | None = None
    layout: str | None = None
    hidden: bool = False
    paragraphs: list[MemoryParagraph] = field(default_factory=list)
    formatting: list[FormatIntent] = field(default_factory=list)


def _splice_utf16(s: str, start: int, end: int, insert: str) -> str:
    raw = s.encode("utf-16-le")
    ins = insert.encode("utf-16-le")
    return (raw[: start * 2] + ins + raw[end * 2 :]).decode("utf-16-le")


def _project_tab(tab: MemoryTab) -> DocumentSegment:
    blocks: list[DocumentBlock] = []
    paragraphs: list[DocumentParagraph] = []
    cursor = 1
    for idx, p in enumerate(tab.paragraphs):
        full = f"{p.text}\n"
        start = cursor
        end = cursor + utf16_len(full)
        paragraphs.append(DocumentParagraph(full, start, end, p.named_style))
        blocks.append(DocumentBlock("paragraph", start, end, idx))
        cursor = end
    return DocumentSegment(
        tab_id=tab.id,
        title=tab.title,
        body_start_index=1,
        body_end_index=cursor,
        blocks=blocks,
        paragraphs=paragraphs,
    )


class MemoryDocument:
    """Pure-Python in-memory document implementing `Backend`."""

    def __init__(self, *paragraphs: str) -> None:
        self.id = "mem-doc-1"
        self.revision_id = "rev-1"
        self.tabs: list[MemoryTab] = [
            MemoryTab(paragraphs=[MemoryParagraph(p) for p in paragraphs])
        ]

    def add_tab(self, tab_id: str, title: str, *paragraphs: str) -> MemoryTab:
        tab = MemoryTab(id=tab_id, title=title, paragraphs=[MemoryParagraph(p) for p in paragraphs])
        self.tabs.append(tab)
        return tab

    def paragraph_texts(self, tab_id: str = "") -> list[str]:
        return [p.text for p in self._find_tab(tab_id).paragraphs]

    def plain_text(self, tab_id: str = "") -> str:
        return "\n".join(self.paragraph_texts(tab_id))

    def project(self) -> DocumentProjection:
        tabs: list[DocumentSegment] = []
        legacy: DocumentSegment | None = None
        for i, tab in enumerate(self.tabs):
            seg = _project_tab(tab)
            if i == 0 and tab.id == "":
                legacy = seg
            tabs.append(seg)
        return DocumentProjection(self.id, self.revision_id, legacy, tabs)

    def apply_text_plan(self, tab_id: str, plan: TextPlan) -> None:
        tab = self._find_tab(tab_id)
        for edit in sorted(plan.text_edits, key=lambda e: e.start_index, reverse=True):
            seg = _project_tab(tab)
            for i, p in enumerate(seg.paragraphs):
                if edit.start_index >= p.start_index and edit.end_index <= p.end_index:
                    updated = _splice_utf16(
                        p.text,
                        edit.start_index - p.start_index,
                        edit.end_index - p.start_index,
                        edit.insert_text,
                    )
                    trimmed = updated[:-1] if updated.endswith("\n") else updated
                    style = tab.paragraphs[i].named_style
                    tab.paragraphs[i : i + 1] = [MemoryParagraph(part, style) for part in trimmed.split("\n")]
                    break
        tab.formatting.extend(plan.formatting)

    def apply_address_mutations(self, tab_id: str, mutations: list[AddressMutation]) -> None:
        tab = self._find_tab(tab_id)
        ordered = sorted(mutations, key=lambda m: (m.start_index, m.end_index), reverse=True)
        for m in ordered:
            seg = _project_tab(tab)
            if m.insert_text is not None and (m.end_index == 0 or m.end_index == m.start_index):
                is_append = m.insert_text.startswith("\n")
                cleaned = m.insert_text[1:] if is_append else m.insert_text
                if cleaned.endswith("\n"):
                    cleaned = cleaned[:-1]
                new_paras = [MemoryParagraph(t) for t in cleaned.split("\n")]
                inserted = False
                for i, b in enumerate(seg.blocks):
                    if is_append and m.start_index in (b.end_index - 1, b.end_index):
                        tab.paragraphs[i + 1 : i + 1] = new_paras
                        inserted = True
                        break
                    if not is_append and m.start_index == b.start_index:
                        tab.paragraphs[i:i] = new_paras
                        inserted = True
                        break
                if not inserted:
                    tab.paragraphs.extend(new_paras)
                continue

            if len(seg.blocks) == 1 and m.start_index >= seg.blocks[0].start_index and m.end_index <= seg.blocks[0].end_index:
                tab.paragraphs[0].text = ""
                continue

            kept: list[MemoryParagraph] = []
            for i, b in enumerate(seg.blocks):
                if m.start_index == b.end_index - 1 and m.end_index > b.end_index:
                    kept.append(tab.paragraphs[i])
                    continue
                if (b.start_index >= m.start_index and b.end_index <= m.end_index) or (
                    b.start_index >= m.start_index and b.end_index - 1 <= m.end_index and i == len(seg.blocks) - 1
                ):
                    continue
                kept.append(tab.paragraphs[i])
            tab.paragraphs = kept if kept else [MemoryParagraph("")]

    def apply_transliterate(
        self, tab_id: str, source: str, dest: str, targets: list[AddressElement]
    ) -> int:
        tab = self._find_tab(tab_id)
        mapping = dict(zip(source, dest))
        target_nums = {t.number for t in targets}
        changed = 0
        for idx, p in enumerate(tab.paragraphs, start=1):
            if target_nums and idx not in target_nums:
                continue
            chars: list[str] = []
            for ch in p.text:
                if ch in mapping:
                    chars.append(mapping[ch])
                    changed += 1
                else:
                    chars.append(ch)
            p.text = "".join(chars)
        return changed

    def apply_container_op(self, scope: ContainerScope, expr: Expression) -> int:
        indices = self._resolve_container_indices(scope)
        if expr.command == "d":
            for idx in reversed(indices):
                self.tabs.pop(idx)
            return len(indices)
        if expr.command in ("a", "i"):
            title = expr.replacement.strip() or f"Tab {len(self.tabs) + 1}"
            new_tab = MemoryTab(
                id=f"tab-{len(self.tabs) + 1}",
                title=title,
                layout=expr.brace.layout if expr.brace else None,
                paragraphs=[MemoryParagraph(title)],
            )
            anchor = indices[-1] if indices else len(self.tabs) - 1
            pos = anchor + 1 if expr.command == "a" else anchor
            self.tabs.insert(pos, new_tab)
            return 1
        if expr.command == "brace" and expr.brace:
            for idx in indices:
                t = self.tabs[idx]
                if expr.brace.bg:
                    t.background = expr.brace.bg
                if expr.brace.notes:
                    t.notes = expr.brace.notes
                if expr.brace.transition:
                    t.transition = expr.brace.transition
                if expr.brace.layout:
                    t.layout = expr.brace.layout
                if expr.brace.hide:
                    t.hidden = True
            return len(indices)
        return 0

    def _resolve_container_indices(self, scope: ContainerScope) -> list[int]:
        if scope.all:
            return list(range(len(self.tabs)))
        if scope.name:
            low = scope.name.lower()
            for i, t in enumerate(self.tabs):
                if t.id == scope.name or t.title.lower() == low:
                    return [i]
            raise SedmatError(f'container "{scope.name}" not found')
        if scope.address:
            total = len(self.tabs)
            if total == 0:
                raise SedmatError("document has no containers")
            start = total if scope.address.start == -1 else scope.address.start
            end = start if not scope.address.has_range else (total if scope.address.end == -1 else scope.address.end)
            if start < 1 or start > total or end < 1 or end > total or end < start:
                raise SedmatError("container address out of range")
            return list(range(start - 1, end))
        return [0] if self.tabs else []

    def _find_tab(self, tab_id: str) -> MemoryTab:
        if not tab_id:
            if not self.tabs:
                self.tabs.append(MemoryTab())
            return self.tabs[0]
        low = tab_id.lower()
        for t in self.tabs:
            if t.id == tab_id or t.title.lower() == low:
                return t
        raise SedmatError(f'tab "{tab_id}" not found')


class Executor:
    def __init__(self, backend: Backend) -> None:
        self.backend = backend

    def execute_string(self, script: str, opts: ExecuteOptions | None = None) -> ExecutionReport:
        return self.execute(parse_program(script), opts)

    def execute(self, program: Program, opts: ExecuteOptions | None = None) -> ExecutionReport:
        options = opts or ExecuteOptions()
        enriched = enrich(program)
        report = ExecutionReport(dry_run=options.dry_run)

        for expr in enriched.expressions:
            if expr.container and (expr.container.container_op or expr.command == "brace"):
                n = 1 if options.dry_run else self.backend.apply_container_op(expr.container, expr)
                report.total_matches += n
                continue

            proj = self.backend.project()
            tab_id = _resolve_tab_id(proj, expr, options.tab_id)
            seg = select_segment(proj, tab_id)

            if expr.command == "s":
                if expr.address:
                    targets = resolve_address(expr.address, address_elements(seg))
                    paragraphs = [
                        DocumentParagraph(f"{t.text}\n", t.start_index, t.end_index)
                        for t in targets
                        if t.kind == "paragraph"
                    ]
                else:
                    paragraphs = seg.paragraphs
                plan = plan_paragraph_substitutions(paragraphs, expr)
                report.total_matches += plan.match_count
                if not options.dry_run and plan.match_count > 0:
                    self.backend.apply_text_plan(tab_id, plan)
            elif expr.command == "d":
                elements = address_elements(seg)
                targets = resolve_address(expr.address, elements) if expr.address else list(elements)
                if expr.pattern:
                    rx = compile_sed_regex(expr.pattern)
                    targets = [t for t in targets if rx.search(t.text)]
                mutations = plan_addressed_delete(elements, targets)
                report.total_matches += len(targets)
                if not options.dry_run and mutations:
                    self.backend.apply_address_mutations(tab_id, mutations)
            elif expr.command in ("a", "i"):
                elements = address_elements(seg)
                if expr.address:
                    targets = resolve_address(expr.address, elements)
                else:
                    rx = compile_sed_regex(expr.pattern)
                    targets = [e for e in elements if rx.search(e.text)]
                mutations = (
                    plan_addressed_insert(targets, expr.replacement)
                    if expr.command == "i"
                    else plan_addressed_append(targets, expr.replacement)
                )
                report.total_matches += len(targets)
                if not options.dry_run and mutations:
                    self.backend.apply_address_mutations(tab_id, mutations)
            elif expr.command == "y":
                targets = resolve_address(expr.address, address_elements(seg)) if expr.address else []
                if not options.dry_run:
                    report.total_matches += self.backend.apply_transliterate(
                        tab_id, expr.pattern, expr.replacement, targets
                    )
        return report


def _resolve_tab_id(proj: DocumentProjection, expr: Expression, default_tab: str) -> str:
    scope = expr.container
    if not scope:
        return default_tab
    if scope.name:
        return scope.name
    if scope.address:
        total = len(proj.tabs)
        idx = total if scope.address.start == -1 else scope.address.start
        if idx < 1 or idx > total:
            raise SedmatError("container address out of range")
        t = proj.tabs[idx - 1]
        return t.tab_id or t.title
    return default_tab
