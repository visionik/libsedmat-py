from __future__ import annotations

from pathlib import Path
import re

from .brace import (
    find_matching_brace,
    has_brace_formatting,
    merge_brace_spans,
    parse_brace_expression,
    parse_brace_replacement,
)
from .types import Address, ContainerScope, Expression, Program, SedmatError, TableCreateSpec

_CONTAINER_TYPES = {"slide", "sheet", "tab", "page", "section"}
_REGION_RE = re.compile(r"^(title|sub|subtitle|body|notes|header|footer|shape=[1-9]\d*)$", re.I)


def parse_address(raw: str) -> tuple[Address | None, str]:
    if not raw or (raw[0] != "$" and not raw[0].isdigit()):
        return None, raw

    i = 0
    if raw[i] == "$":
        start = -1
        i += 1
    else:
        s_idx = i
        while i < len(raw) and raw[i].isdigit():
            i += 1
        start = int(raw[s_idx:i])
        if start < 1:
            raise SedmatError(f"address must be >= 1, got {start}")

    has_range = False
    end = 0
    if i < len(raw) and raw[i] == ",":
        if start == -1:
            raise SedmatError("'$' cannot be used as range start")
        has_range = True
        i += 1
        if i >= len(raw):
            raise SedmatError("missing range end after ','")
        if raw[i] == "$":
            end = -1
            i += 1
        elif raw[i].isdigit():
            e_idx = i
            while i < len(raw) and raw[i].isdigit():
                i += 1
            end = int(raw[e_idx:i])
            if end < 1:
                raise SedmatError(f"address range end must be >= 1, got {end}")
            if end < start:
                raise SedmatError(f"address range {start},{end} is reversed")
        else:
            raise SedmatError(f"invalid range end in {raw}")

    rest = raw[i:]
    if not rest:
        raise SedmatError(f"address without command: {raw}")
    return Address(start=start, end=end, has_range=has_range), rest


def parse_container_scope(raw: str) -> tuple[ContainerScope | None, str]:
    if not raw.startswith("@"):
        return None, raw
    rest = raw[1:]
    if not rest:
        raise SedmatError("empty container scope '@'")

    m_bare = re.match(r"^(header|footer):(.+)$", rest, re.I)
    if m_bare:
        return ContainerScope(region=m_bare.group(1).lower(), container_op=False), m_bare.group(2)

    container_type: str | None = None
    m_type = re.match(r"^([a-z]+)=", rest)
    if m_type and m_type.group(1) in _CONTAINER_TYPES:
        container_type = m_type.group(1)
        rest = rest[len(m_type.group(0)):]

    address: Address | None = None
    all_flag = False
    name: str | None = None

    if rest.startswith("*"):
        all_flag = True
        rest = rest[1:]
    elif rest.startswith('"'):
        end_q = rest.find('"', 1)
        if end_q < 0:
            raise SedmatError(f"unterminated quoted container name: {raw}")
        name = rest[1:end_q]
        rest = rest[end_q + 1:]
    elif rest.startswith("$") or (rest and rest[0].isdigit()):
        idx = 0
        if rest[idx] == "$":
            idx += 1
        else:
            while idx < len(rest) and rest[idx].isdigit():
                idx += 1
        if idx < len(rest) and rest[idx] == ",":
            idx += 1
            if idx < len(rest) and rest[idx] == "$":
                idx += 1
            else:
                while idx < len(rest) and rest[idx].isdigit():
                    idx += 1
        address, _ = parse_address(rest[:idx] + "d")
        rest = rest[idx:]
    else:
        m_name = re.match(r"^[A-Za-z0-9_-]+", rest)
        if not m_name:
            raise SedmatError(f"invalid container target: {raw}")
        name = m_name.group(0)
        rest = rest[len(name):]

    if rest.startswith(":"):
        body = rest[1:]
        region: str | None = None
        if ":" in body:
            cand, after = body.split(":", 1)
            if _REGION_RE.match(cand):
                region = cand.lower()
                body = after
        if not body:
            raise SedmatError(f"container scope without command: {raw}")
        return (
            ContainerScope(
                container_type=container_type,
                address=address,
                all=all_flag,
                name=name,
                region=region,
                container_op=False,
            ),
            body,
        )

    if rest and rest[0] in ("d", "a", "i", "{"):
        return (
            ContainerScope(
                container_type=container_type,
                address=address,
                all=all_flag,
                name=name,
                container_op=True,
            ),
            rest,
        )

    raise SedmatError(f"invalid container scope: {raw}")


def _split_by_delimiter(value: str, delim: str) -> list[str]:
    parts: list[str] = []
    cur: list[str] = []
    i = 0
    while i < len(value):
        if value[i] == "\\" and i + 1 < len(value):
            if value[i + 1] == delim:
                cur.append(delim)
            else:
                cur.append("\\")
                cur.append(value[i + 1])
            i += 2
            continue
        if value[i] == delim:
            parts.append("".join(cur))
            cur.clear()
        else:
            cur.append(value[i])
        i += 1
    parts.append("".join(cur))
    return parts


def _apply_regex_flags(pattern: str, flags: str) -> str:
    res = pattern
    if "i" in flags and not res.startswith("(?i)"):
        res = f"(?i){res}"
    if "m" in flags and not res.startswith("(?m)"):
        res = f"(?m){res}"
    return res


def _nth_flag(flags: str) -> int:
    m = re.search(r"(\d+)", flags)
    return int(m.group(1)) if m else 0


def parse_expression(raw: str) -> Expression:
    trimmed = raw.strip()
    if not trimmed:
        raise SedmatError("empty expression")

    container, after_container = parse_container_scope(trimmed)
    if container is not None and after_container.startswith("{"):
        close = find_matching_brace(after_container, 0)
        if close != len(after_container) - 1:
            raise SedmatError(f"malformed container brace expression: {raw}")
        brace = parse_brace_expression(after_container[1:close])
        return Expression(
            command="brace",
            replacement=after_container,
            container=container,
            brace=brace,
            enriched=True,
        )

    if container is not None and container.container_op:
        address, body = None, after_container
    else:
        address, body = parse_address(after_container)
    has_addr = address is not None or container is not None

    cmd = body[0]
    if cmd == "s":
        if len(body) < 4:
            raise SedmatError(f"invalid substitution: {raw}")
        delim = body[1]
        if delim.isalnum() or delim == "\\":
            raise SedmatError(f"invalid delimiter '{delim}'")
        parts = _split_by_delimiter(body[2:], delim)
        if len(parts) < 3 or len(parts) > 4:
            raise SedmatError(f"malformed substitution: {raw}")
        flags = parts[2]
        expr = Expression(
            command="s",
            pattern=_apply_regex_flags(parts[0], flags),
            replacement=parts[1],
            global_flag="g" in flags,
            nth_match=_nth_flag(flags),
            flags=flags,
        )
    elif cmd == "d":
        if body == "d":
            if not has_addr:
                raise SedmatError("delete command 'd' requires a pattern or address")
            expr = Expression(command="d")
        else:
            delim = body[1]
            parts = _split_by_delimiter(body[2:], delim)
            if len(parts) < 2:
                raise SedmatError(f"malformed delete: {raw}")
            flags = parts[1]
            expr = Expression(
                command="d",
                pattern=_apply_regex_flags(parts[0], flags),
                global_flag="g" in flags,
                flags=flags,
            )
    elif cmd in ("a", "i"):
        if len(body) < 3:
            raise SedmatError(f"invalid {cmd} command: {raw}")
        delim = body[1]
        parts = _split_by_delimiter(body[2:], delim)
        if has_addr:
            if len(parts) < 2:
                raise SedmatError(f"malformed addressed {cmd}: {raw}")
            expr = Expression(command=cmd, replacement=parts[0], flags=parts[1])
        else:
            if len(parts) < 3:
                raise SedmatError(f"malformed {cmd}: {raw}")
            flags = parts[2]
            expr = Expression(
                command=cmd,
                pattern=_apply_regex_flags(parts[0], flags),
                replacement=parts[1],
                global_flag="g" in flags,
                flags=flags,
            )
    elif cmd == "y":
        if len(body) < 4:
            raise SedmatError(f"invalid transliterate: {raw}")
        delim = body[1]
        parts = _split_by_delimiter(body[2:], delim)
        if len(parts) < 3:
            raise SedmatError(f"malformed transliterate: {raw}")
        if len(parts[0]) != len(parts[1]):
            raise SedmatError("transliterate source and dest lengths differ")
        expr = Expression(command="y", pattern=parts[0], replacement=parts[1], flags=parts[2])
    else:
        raise SedmatError(f"unsupported command: {raw}")

    expr.address = address
    expr.container = container
    return expr


def parse(raw: str) -> Program:
    return Program(expressions=[parse_expression(raw)])


def enrich(program: Program) -> Program:
    for expr in program.expressions:
        if expr.enriched or expr.command != "s":
            continue
        expr.enriched = True
        if has_brace_formatting(expr.replacement):
            cleaned, spans = parse_brace_replacement(expr.replacement)
            if spans:
                expr.replacement = cleaned
                expr.brace_spans = spans
                if len(spans) == 1 and spans[0].is_global:
                    expr.brace = spans[0].expr
                else:
                    expr.brace = merge_brace_spans(spans)
                if expr.brace and expr.brace.table_ref:
                    m = re.fullmatch(r"(\d+)[xX](\d+)(:header)?", expr.brace.table_ref)
                    if m:
                        expr.table_create = TableCreateSpec(
                            rows=int(m.group(1)),
                            columns=int(m.group(2)),
                            header=bool(m.group(3)),
                        )
                        expr.brace = None
                        expr.brace_spans = []
    return program


def parse_program(script: str) -> Program:
    expressions: list[Expression] = []
    for idx, line in enumerate(script.splitlines(), start=1):
        trimmed = line.strip()
        if not trimmed or trimmed.startswith("#"):
            continue
        try:
            expressions.append(parse_expression(trimmed))
        except SedmatError as exc:
            raise SedmatError(f"line {idx}: {exc}") from exc
    return enrich(Program(expressions=expressions))


def parse_file(path: str | Path) -> Program:
    return parse_program(Path(path).read_text(encoding="utf-8"))
