"""Data model for xschem .sch/.sym file elements.

Each element type corresponds to a line prefix in the xschem file format.
Elements store their original text (raw_line) for round-trip fidelity —
to_line() returns raw_line if unmodified, regenerates from fields if dirty.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pyxschem.attributes import serialize_attributes


def _fmt_num(v: float) -> str:
    """Format a number: 300.0 → '300', 63.75 → '63.75'."""
    if v == int(v):
        return str(int(v))
    return str(v)


@dataclass
class Header:
    """The file header block (v, G, K, V, S, E lines).

    Stored as raw lines since these are rarely modified programmatically.
    """

    raw_lines: list[str] = field(default_factory=list)

    def to_lines(self) -> list[str]:
        return list(self.raw_lines)


@dataclass
class Component:
    """A component instance (C line).

    Format: C {symbol} x y rotation mirror {attributes}
    """

    symbol: str
    x: float
    y: float
    rotation: int
    mirror: int
    attributes: dict[str, str] = field(default_factory=dict)
    raw_line: str | None = None

    def to_line(self) -> str:
        if self.raw_line is not None:
            return self.raw_line
        attrs = serialize_attributes(self.attributes)
        return f"C {{{self.symbol}}} {_fmt_num(self.x)} {_fmt_num(self.y)} {self.rotation} {self.mirror} {attrs}"

    def set_attribute(self, key: str, value: str) -> None:
        self.attributes[key] = value
        self.raw_line = None

    @property
    def name(self) -> str | None:
        return self.attributes.get("name")

    @property
    def value(self) -> str | None:
        return self.attributes.get("value")

    @property
    def position(self) -> tuple[float, float]:
        return (self.x, self.y)


@dataclass
class Net:
    """A wire/net segment (N line).

    Format: N x1 y1 x2 y2 {attributes}
    """

    x1: float
    y1: float
    x2: float
    y2: float
    attributes: dict[str, str] = field(default_factory=dict)
    raw_line: str | None = None

    def to_line(self) -> str:
        if self.raw_line is not None:
            return self.raw_line
        attrs = serialize_attributes(self.attributes)
        return f"N {_fmt_num(self.x1)} {_fmt_num(self.y1)} {_fmt_num(self.x2)} {_fmt_num(self.y2)} {attrs}"

    @property
    def label(self) -> str | None:
        return self.attributes.get("lab")


@dataclass
class Text:
    """A text annotation (T line).

    Format: T {text} x y rotation mirror xscale yscale {attributes}
    """

    text: str
    x: float
    y: float
    rotation: int
    mirror: int
    xscale: float
    yscale: float
    attributes: dict[str, str] = field(default_factory=dict)
    raw_line: str | None = None

    def to_line(self) -> str:
        if self.raw_line is not None:
            return self.raw_line
        attrs = serialize_attributes(self.attributes)
        return f"T {{{self.text}}} {_fmt_num(self.x)} {_fmt_num(self.y)} {self.rotation} {self.mirror} {self.xscale} {self.yscale} {attrs}"


@dataclass
class GraphicLine:
    """A graphical line (L line).

    Format: L layer x1 y1 x2 y2 {attributes}
    """

    layer: int
    x1: float
    y1: float
    x2: float
    y2: float
    attributes: dict[str, str] = field(default_factory=dict)
    raw_line: str | None = None

    def to_line(self) -> str:
        if self.raw_line is not None:
            return self.raw_line
        attrs = serialize_attributes(self.attributes)
        return f"L {self.layer} {_fmt_num(self.x1)} {_fmt_num(self.y1)} {_fmt_num(self.x2)} {_fmt_num(self.y2)} {attrs}"


@dataclass
class Box:
    """A graphical box/rectangle (B line).

    Format: B layer x1 y1 x2 y2 {attributes}
    """

    layer: int
    x1: float
    y1: float
    x2: float
    y2: float
    attributes: dict[str, str] = field(default_factory=dict)
    raw_line: str | None = None

    def to_line(self) -> str:
        if self.raw_line is not None:
            return self.raw_line
        attrs = serialize_attributes(self.attributes)
        return f"B {self.layer} {_fmt_num(self.x1)} {_fmt_num(self.y1)} {_fmt_num(self.x2)} {_fmt_num(self.y2)} {attrs}"


@dataclass
class Arc:
    """A graphical arc (A line).

    Format: A layer x y r start_angle sweep_angle {attributes}
    """

    layer: int
    x: float
    y: float
    r: float
    start_angle: float
    sweep_angle: float
    attributes: dict[str, str] = field(default_factory=dict)
    raw_line: str | None = None

    def to_line(self) -> str:
        if self.raw_line is not None:
            return self.raw_line
        attrs = serialize_attributes(self.attributes)
        return f"A {self.layer} {_fmt_num(self.x)} {_fmt_num(self.y)} {_fmt_num(self.r)} {_fmt_num(self.start_angle)} {_fmt_num(self.sweep_angle)} {attrs}"


@dataclass
class Polygon:
    """A polygon (P line).

    Format: P layer npoints x1 y1 x2 y2 ... {attributes}
    """

    layer: int
    points: list[tuple[float, float]] = field(default_factory=list)
    attributes: dict[str, str] = field(default_factory=dict)
    raw_line: str | None = None

    def to_line(self) -> str:
        if self.raw_line is not None:
            return self.raw_line
        coords = " ".join(f"{_fmt_num(x)} {_fmt_num(y)}" for x, y in self.points)
        attrs = serialize_attributes(self.attributes)
        return f"P {self.layer} {len(self.points)} {coords} {attrs}"


@dataclass
class RawLine:
    """A catch-all for unknown or future line types.

    Preserves round-trip fidelity for lines the library doesn't parse.
    """

    line: str

    def to_line(self) -> str:
        return self.line


# Union type for all element types
Element = Header | Component | Net | Text | GraphicLine | Box | Arc | Polygon | RawLine
