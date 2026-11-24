from __future__ import annotations

import re

from .types import (
    Address,
    AddressElement,
    AddressMutation,
    DocumentParagraph,
    DocumentProjection,
    DocumentSegment,
    DocumentTable,
    Expression,
    FormatIntent,
    SedmatError,
    TextEdit,
    TextPlan,
)


def utf16_len(s: str) -> int:
    return len(s.encode("utf-16-le")) // 2


def compile_sed_regex(pattern: str) -> re.Pattern[str]:
    flags = 0
    body = pattern
    while True:
        if body.startswith("(?i)"):
            flags |= re.IGNORECASE
            body = body[4:]
        elif body.startswith("(?m)"):
            flags |= re.MULTILINE
            body = body[4:]
        elif body.startswith(("(?im)", "(?mi)")):
            flags |= re.IGNORECASE | re.MULTILINE
            body = body[5:]
        else:
            break
    return re.compile(body, flags)


def expand_replacement(template: str, match: re.Match[str]) -> str:
    def get_group(idx: int) -> str:
        try:
            val = match.group(idx)
            return val if val is not None else ""
        except IndexError:
            return ""

    out: list[str] = []
    i = 0
    while i < len(template):
        ch = template[i]
        if ch == "\\" and i + 1 < len(template):
            nxt = template[i + 1]
            if nxt == "&":
                out.append("&")
                i += 2
                continue
            if nxt == "n":
                out.append("\n")
                i += 2
                continue
            if "1" <= nxt <= "9":
                out.append(get_group(int(nxt)))
                i += 2
                continue
        if ch == "&":
            out.append(get_group(0))
            i += 1
            continue
        if ch == "$" and i + 1 < len(template):
            nxt = template[i + 1]
            if nxt == "$":
                out.append("$")
                i += 2
                continue
            if "0" <= nxt <= "9":
                out.append(get_group(int(nxt)))
                i += 2
                continue
            if nxt == "{":
                close = template.find("}", i + 2)
                if close > i + 2 and template[i + 2:close].isdigit():
                    out.append(get_group(int(template[i + 2:close])))
                    i = close + 1
                    continue
        out.append(ch)
        i += 1
    return "".join(out)


def _table_preview(t: DocumentTable) -> str:
    if not t.rows:
        return "[empty table]"
    preview = " | ".join(c.text.rstrip("\n").strip() for c in t.rows[0].cells)
    return preview[:57] + "..." if len(preview) > 60 else preview


def address_elements(seg: DocumentSegment) -> list[AddressElement]:
    out: list[AddressElement] = []
    num = 0
    for block in seg.blocks:
        if block.kind == "section_break":
            continue
        num += 1
        if block.kind == "paragraph":
            text = (
                seg.paragraphs[block.item_index].text.rstrip("\n")
                if 0 <= block.item_index < len(seg.paragraphs)
                else ""
            )
            out.append(AddressElement(num, "paragraph", text, block.start_index, block.end_index))
        elif block.kind == "table":
            text = (
                _table_preview(seg.tables[block.item_index])
                if 0 <= block.item_index < len(seg.tables)
                else "[empty table]"
            )
            out.append(AddressElement(num, "table", text, block.start_index, block.end_index))
        elif block.kind == "table_of_contents":
            out.append(AddressElement(num, "toc", "[table of contents]", block.start_index, block.end_index))
    return out


def select_segment(proj: DocumentProjection, tab_id: str = "") -> DocumentSegment:
    if tab_id:
        low = tab_id.lower()
        for tab in proj.tabs:
            if tab.tab_id == tab_id or tab.title.lower() == low:
                return tab
        raise SedmatError(f'tab "{tab_id}" not found')
    if proj.legacy is not None:
        return proj.legacy
    if proj.tabs:
        return proj.tabs[0]
    raise SedmatError("document has no content")


def format_structure(seg: DocumentSegment) -> str:
    lines: list[str] = []
    num = 0
    for block in seg.blocks:
        if block.kind == "section_break":
            continue
        num += 1
        if block.kind == "paragraph":
            p = seg.paragraphs[block.item_index]
            style = p.named_style or "NORMAL_TEXT"
            text = p.text.rstrip("\n")
            lines.append(f'[{num}] paragraph ({style}): "{text}"')
        elif block.kind == "table":
            t = seg.tables[block.item_index]
            rows = len(t.rows) or t.declared_rows
            cols = len(t.rows[0].cells) if t.rows else t.declared_columns
            lines.append(f'[{num}] table ({rows}x{cols}): "{_table_preview(t)}"')
        elif block.kind == "table_of_contents":
            lines.append(f'[{num}] toc: "[table of contents]"')
    return "\n".join(lines) + ("\n" if lines else "")


def format_numbered(seg: DocumentSegment) -> str:
    elems = address_elements(seg)
    return "".join(f"[{el.number}] {el.text}\n" for el in elems)


def resolve_address(address: Address, elements: list[AddressElement]) -> list[AddressElement]:
    if not elements:
        raise SedmatError("document has no paragraphs")
    last = len(elements)
    start = last if address.start == -1 else address.start
    if start < 1 or start > last:
        raise SedmatError(f"address {start} out of range (document has {last} paragraphs)")
    if not address.has_range:
        return [elements[start - 1]]
    end = start if address.end == 0 else (last if address.end == -1 else address.end)
    if end < 1 or end > last:
        raise SedmatError(f"address end {end} out of range (document has {last} paragraphs)")
    if end < start:
        raise SedmatError(f"address range {start},{end} is reversed")
    return elements[start - 1:end]


def _is_contiguous_terminal_range(elements: list[AddressElement], targets: list[AddressElement]) -> bool:
    if len(targets) < 2 or targets[-1].number != len(elements):
        return False
    return all(targets[i].number == targets[i - 1].number + 1 for i in range(1, len(targets)))


def plan_addressed_delete(elements: list[AddressElement], targets: list[AddressElement]) -> list[AddressMutation]:
    if not targets:
        return []
    if _is_contiguous_terminal_range(elements, targets):
        return [AddressMutation(targets[0].start_index, targets[-1].end_index - 1)]
    mutations: list[AddressMutation] = []
    for t in targets:
        start_idx, end_idx = t.start_index, t.end_index
        is_last = t.number == len(elements)
        if is_last and t.number > 1:
            start_idx = elements[t.number - 2].end_index - 1
            end_idx = t.end_index - 1
        elif is_last and t.number == 1:
            if t.start_index >= t.end_index - 1:
                continue
            end_idx = t.end_index - 1
        mutations.append(AddressMutation(start_idx, end_idx))
    return mutations


def plan_addressed_insert(targets: list[AddressElement], replacement: str) -> list[AddressMutation]:
    text = replacement.replace("\\n", "\n")
    if not text.endswith("\n"):
        text += "\n"
    return [AddressMutation(t.start_index, t.start_index, text) for t in targets]


def plan_addressed_append(targets: list[AddressElement], replacement: str) -> list[AddressMutation]:
    text = replacement.replace("\\n", "\n")
    text = "\n" + (text[:-1] if text.endswith("\n") else text)
    return [AddressMutation(t.end_index - 1, t.end_index - 1, text) for t in targets]


def plan_paragraph_substitutions(paragraphs: list[DocumentParagraph], expr: Expression) -> TextPlan:
    rx = compile_sed_regex(expr.pattern)
    plan = TextPlan()
    text_delta = 0

    for para in paragraphs:
        if not para.text:
            continue
        matches = list(rx.finditer(para.text))
        if expr.nth_match > 0:
            matches = [matches[expr.nth_match - 1]] if len(matches) >= expr.nth_match else []
        elif not expr.global_flag:
            matches = matches[:1]

        for m in matches:
            old_text = m.group(0)
            expanded = expand_replacement(expr.replacement, m)
            if (
                expanded == ""
                and expr.replacement == ""
                and expr.brace is not None
                and not expr.brace.has_break
                and not expr.brace.has_toc
                and not expr.brace.img_ref
                and not expr.brace.table_ref
            ):
                expanded = old_text
            start = para.start_index + utf16_len(para.text[:m.start()])
            match_u16 = utf16_len(old_text)
            end = start + match_u16
            plan.match_count += 1
            plan.text_edits.append(TextEdit(start, end, expanded))
            ins_u16 = utf16_len(expanded)
            if expr.brace is not None and expanded:
                f_start = start + text_delta
                plan.formatting.append(FormatIntent(f_start, f_start + ins_u16, [], expr.brace))
            text_delta += ins_u16 - match_u16
    return plan
