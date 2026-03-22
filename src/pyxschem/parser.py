"""Parse and serialize xschem .sch/.sym files.

Converts between raw text and lists of typed model elements.
Preserves raw_line on every element for round-trip fidelity.
"""

from __future__ import annotations

from pyxschem.attributes import parse_attributes
from pyxschem.model import (
    Arc,
    Box,
    Component,
    Element,
    GraphicLine,
    Header,
    Net,
    Polygon,
    RawLine,
    Text,
)


def parse_schematic(text: str) -> list[Element]:
    """Parse .sch file text into a list of typed elements.

    Args:
        text: Full content of a .sch or .sym file.

    Returns:
        List of Element instances. Header is first if present.
    """
    if not text:
        return []

    logical_lines = _split_logical_lines(text)
    elements: list[Element] = []
    header_lines: list[str] = []
    in_header = True

    for line in logical_lines:
        if not line:
            # Preserve empty lines
            if in_header:
                header_lines.append(line)
            else:
                elements.append(RawLine(line=""))
            continue

        prefix = line[0]

        if in_header and prefix in "vGKVSEF":
            header_lines.append(line)
            if prefix == "E":
                elements.append(Header(raw_lines=header_lines))
                in_header = False
            continue

        # Past header — if we collected header lines but never got E,
        # flush them anyway
        if in_header and header_lines:
            elements.append(Header(raw_lines=header_lines))
            in_header = False

        in_header = False

        if prefix == "C":
            elements.append(_parse_component(line))
        elif prefix == "N":
            elements.append(_parse_net(line))
        elif prefix == "T":
            elements.append(_parse_text(line))
        elif prefix == "L":
            elements.append(_parse_graphic_line(line))
        elif prefix == "B":
            elements.append(_parse_box(line))
        elif prefix == "A":
            elements.append(_parse_arc(line))
        elif prefix == "P":
            elements.append(_parse_polygon(line))
        else:
            elements.append(RawLine(line=line))

    # If file was header-only
    if in_header and header_lines:
        elements.append(Header(raw_lines=header_lines))

    return elements


def serialize_schematic(elements: list[Element]) -> str:
    """Serialize a list of elements back to .sch file text.

    Args:
        elements: List of Element instances.

    Returns:
        File text with trailing newline.
    """
    if not elements:
        return ""

    lines: list[str] = []
    for element in elements:
        if isinstance(element, Header):
            lines.extend(element.to_lines())
        else:
            lines.append(element.to_line())

    return "\n".join(lines) + "\n"


def _split_logical_lines(text: str) -> list[str]:
    """Split text into logical lines, joining multiline attribute blocks.

    A line with unbalanced braces is joined with subsequent lines until
    braces are balanced. Quote state is tracked across joined lines to
    handle multiline quoted values inside brace blocks.
    """
    raw_lines = text.rstrip("\n").split("\n")
    logical: list[str] = []
    i = 0

    while i < len(raw_lines):
        line = raw_lines[i]
        depth, in_quote = _brace_depth(line, False)

        if depth > 0 or in_quote:
            # Unbalanced — accumulate lines until balanced
            parts = [line]
            while (depth > 0 or in_quote) and i + 1 < len(raw_lines):
                i += 1
                parts.append(raw_lines[i])
                d, in_quote = _brace_depth(raw_lines[i], in_quote)
                depth += d
            logical.append("\n".join(parts))
        else:
            logical.append(line)

        i += 1

    return logical


def _brace_depth(line: str, in_quote: bool) -> tuple[int, bool]:
    """Count net brace depth change in a line, tracking quote state.

    Args:
        line: The line to analyze.
        in_quote: Whether we're inside a quoted string from a previous line.

    Returns:
        (depth_change, in_quote_after) — net brace depth and quote state.
    """
    depth = 0
    for ch in line:
        if ch == '"':
            in_quote = not in_quote
        elif not in_quote:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
    return depth, in_quote


def _extract_braced(text: str, start: int) -> tuple[str, int]:
    """Extract content between {} starting at position of opening brace.

    Returns (content, position after closing brace).
    """
    assert text[start] == "{"
    depth = 1
    i = start + 1
    while i < len(text) and depth > 0:
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
        i += 1
    return text[start + 1 : i - 1], i


def _find_last_braced(text: str) -> tuple[str, str]:
    """Find the last {...} block in a line, return (before, block_content).

    Used to split element lines into positional fields + attribute block.
    """
    # Find the last '{' that starts the attribute block
    last_open = text.rfind("{")
    if last_open == -1:
        return text, ""

    # But we need the matching pair — find from the end
    # Walk backwards from end to find the last balanced {} block
    depth = 0
    end = len(text) - 1
    while end >= 0:
        if text[end] == "}":
            depth += 1
            if depth == 1:
                block_end = end
        elif text[end] == "{":
            depth -= 1
            if depth == 0:
                block_start = end
                content = text[block_start + 1 : block_end]
                before = text[:block_start].rstrip()
                return before, content
        end -= 1

    return text, ""


def _parse_component(line: str) -> Component:
    """Parse: C {symbol} x y rotation mirror {attributes}"""
    # Extract symbol (first braced group after 'C ')
    sym_start = line.index("{")
    symbol, after_sym = _extract_braced(line, sym_start)

    # Parse remaining positional fields and attributes
    rest = line[after_sym:].strip()
    before_attrs, attrs_content = _find_last_braced(rest)
    parts = before_attrs.split()

    return Component(
        symbol=symbol,
        x=float(parts[0]),
        y=float(parts[1]),
        rotation=int(parts[2]),
        mirror=int(parts[3]),
        attributes=parse_attributes(attrs_content),
        raw_line=line,
    )


def _parse_net(line: str) -> Net:
    """Parse: N x1 y1 x2 y2 {attributes}"""
    before, attrs_content = _find_last_braced(line)
    parts = before.split()
    # parts[0] is 'N'

    return Net(
        x1=float(parts[1]),
        y1=float(parts[2]),
        x2=float(parts[3]),
        y2=float(parts[4]),
        attributes=parse_attributes(attrs_content),
        raw_line=line,
    )


def _parse_text(line: str) -> Text:
    """Parse: T {text} x y rotation mirror xscale yscale {attributes}"""
    # Extract text (first braced group after 'T ')
    text_start = line.index("{")
    text_content, after_text = _extract_braced(line, text_start)

    # Parse remaining fields and attributes
    rest = line[after_text:].strip()
    before_attrs, attrs_content = _find_last_braced(rest)
    parts = before_attrs.split()

    return Text(
        text=text_content,
        x=float(parts[0]),
        y=float(parts[1]),
        rotation=int(parts[2]),
        mirror=int(parts[3]),
        xscale=float(parts[4]),
        yscale=float(parts[5]),
        attributes=parse_attributes(attrs_content),
        raw_line=line,
    )


def _parse_graphic_line(line: str) -> GraphicLine:
    """Parse: L layer x1 y1 x2 y2 {attributes}"""
    before, attrs_content = _find_last_braced(line)
    parts = before.split()

    return GraphicLine(
        layer=int(parts[1]),
        x1=float(parts[2]),
        y1=float(parts[3]),
        x2=float(parts[4]),
        y2=float(parts[5]),
        attributes=parse_attributes(attrs_content),
        raw_line=line,
    )


def _parse_box(line: str) -> Box:
    """Parse: B layer x1 y1 x2 y2 {attributes}"""
    before, attrs_content = _find_last_braced(line)
    parts = before.split()

    return Box(
        layer=int(parts[1]),
        x1=float(parts[2]),
        y1=float(parts[3]),
        x2=float(parts[4]),
        y2=float(parts[5]),
        attributes=parse_attributes(attrs_content),
        raw_line=line,
    )


def _parse_arc(line: str) -> Arc:
    """Parse: A layer x y r start_angle sweep_angle {attributes}"""
    before, attrs_content = _find_last_braced(line)
    parts = before.split()

    return Arc(
        layer=int(parts[1]),
        x=float(parts[2]),
        y=float(parts[3]),
        r=float(parts[4]),
        start_angle=float(parts[5]),
        sweep_angle=float(parts[6]),
        attributes=parse_attributes(attrs_content),
        raw_line=line,
    )


def _parse_polygon(line: str) -> Polygon:
    """Parse: P layer npoints x1 y1 x2 y2 ... {attributes}"""
    before, attrs_content = _find_last_braced(line)
    parts = before.split()
    # parts[0]='P', parts[1]=layer, parts[2]=npoints, then x y pairs

    layer = int(parts[1])
    npoints = int(parts[2])
    coords = parts[3 : 3 + npoints * 2]
    points = [
        (float(coords[j]), float(coords[j + 1])) for j in range(0, len(coords), 2)
    ]

    return Polygon(
        layer=layer,
        points=points,
        attributes=parse_attributes(attrs_content),
        raw_line=line,
    )
