"""Data model for xschem .sch/.sym file elements.

Each element type corresponds to a line prefix in the xschem file format.
Elements store their original text (raw_line) for round-trip fidelity —
to_line() returns raw_line if unmodified, regenerates from fields if dirty.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from pyxschem.attributes import serialize_attributes


class _DirtyDict(dict):
    """Dict subclass that auto-clears its owner's raw_line on mutation."""

    __slots__ = ("_owner",)

    def __init__(self, *args: object, _owner: object = None, **kwargs: object):
        super().__init__(*args, **kwargs)
        self._owner = _owner

    def _mark(self) -> None:
        if self._owner is not None and hasattr(self._owner, "raw_line"):
            object.__setattr__(self._owner, "raw_line", None)

    def __setitem__(self, key: str, value: str) -> None:
        super().__setitem__(key, value)
        self._mark()

    def __delitem__(self, key: str) -> None:
        super().__delitem__(key)
        self._mark()

    def update(self, *args: object, **kwargs: object) -> None:  # type: ignore[override]
        super().update(*args, **kwargs)
        self._mark()

    def pop(self, *args: object) -> object:  # type: ignore[override]
        existed = args[0] in self
        result = super().pop(*args)
        if existed:
            self._mark()
        return result

    def clear(self) -> None:
        super().clear()
        self._mark()

    def setdefault(self, key: str, default: object = "") -> object:  # type: ignore[override]
        if key not in self:
            result = super().setdefault(key, default)
            self._mark()
            return result
        return super().setdefault(key, default)


class _AutoDirtyMixin:
    """Auto-clear raw_line on field assignment; wrap attributes dicts."""

    def __setattr__(self, name: str, value: object) -> None:
        if name == "attributes" and isinstance(value, dict):
            value = _DirtyDict(value, _owner=self)
        super().__setattr__(name, value)
        if name != "raw_line" and hasattr(self, "raw_line"):
            super().__setattr__("raw_line", None)

    def set_attribute(self, key: str, value: str) -> None:
        """Set an attribute; auto-clears raw_line via _DirtyDict."""
        self.attributes[key] = value

    def mark_dirty(self) -> None:
        """Call after in-place list mutation (e.g. ``points.append()``)."""
        self.raw_line = None


def _fmt_num(v: float) -> str:
    """Format a number: 300.0 → '300', 63.75 → '63.75'."""
    if not math.isfinite(v):
        return format(v, ".10g")
    if v == int(v):
        return str(int(v))
    return format(v, ".10g")


@dataclass
class Header:
    """The file header block (v, G, K, V, S, E/F lines).

    Stored as raw lines since these are rarely modified programmatically.
    """

    raw_lines: list[str] = field(default_factory=list)

    @classmethod
    def default_schematic(
        cls, version: str = "3.4.5", file_version: str = "1.2"
    ) -> Header:
        """Create a default schematic header."""
        return cls(
            raw_lines=[
                f"v {{xschem version={version} file_version={file_version}}}",
                "G {}",
                "K {}",
                "V {}",
                "S {}",
                "E {}",
            ]
        )

    @classmethod
    def default_symbol(
        cls, version: str = "3.4.5", file_version: str = "1.2"
    ) -> Header:
        """Create a default symbol header."""
        return cls(
            raw_lines=[
                f"v {{xschem version={version} file_version={file_version}}}",
                "G {}",
                "K {}",
                "V {}",
                "S {}",
                "F {}",
                "E {}",
            ]
        )

    def to_lines(self) -> list[str]:
        return list(self.raw_lines)

    # -- K-block (and other single-letter sections) accessors --

    def get_block(self, prefix: str) -> str | None:
        """Return the brace-content of a header block (e.g. ``"K"``).

        Returns ``None`` if the block isn't present.  An empty
        ``K {}`` returns ``""``.
        """
        from pyxschem.parser import extract_braced

        marker = prefix + " "
        for line in self.raw_lines:
            if line.startswith(marker):
                brace_start = line.find("{")
                if brace_start == -1:
                    return None
                content, _ = extract_braced(line, brace_start)
                return content
        return None

    def set_block(self, prefix: str, content: str) -> None:
        """Replace (or insert) a header block by its single-letter prefix.

        ``content`` is the brace body without the surrounding ``{ }``.
        Pass ``""`` to clear a block (renders as ``K {}``).  If the
        block doesn't exist it is appended just before the trailing
        ``E {}`` marker; otherwise the existing line is overwritten.
        """
        new_line = f"{prefix} {{{content}}}"
        marker = prefix + " "
        for i, line in enumerate(self.raw_lines):
            if line.startswith(marker):
                self.raw_lines[i] = new_line
                return
        # Insert before the closing E block when possible.
        for i, line in enumerate(self.raw_lines):
            if line.startswith("E "):
                self.raw_lines.insert(i, new_line)
                return
        self.raw_lines.append(new_line)

    def k_attributes(self) -> dict[str, str]:
        """Parsed K-block attributes (empty dict if ``K {}`` or absent)."""
        from pyxschem.attributes import parse_attributes

        content = self.get_block("K")
        if not content:
            return {}
        return parse_attributes(content)

    def set_k_attributes(self, attrs: dict[str, str]) -> None:
        """Replace the K-block contents with the given attribute dict."""
        from pyxschem.attributes import serialize_attributes

        if not attrs:
            self.set_block("K", "")
            return
        # serialize_attributes returns "{...}" — strip the outer braces.
        body = serialize_attributes(attrs)
        if body.startswith("{") and body.endswith("}"):
            body = body[1:-1]
        self.set_block("K", body)


@dataclass
class Component(_AutoDirtyMixin):
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
        return (
            f"C {{{self.symbol}}} {_fmt_num(self.x)} {_fmt_num(self.y)}"
            f" {self.rotation} {self.mirror} {attrs}"
        )

    @property
    def name(self) -> str | None:
        return self.attributes.get("name")

    @property
    def value(self) -> str | None:
        return self.attributes.get("value")

    @property
    def label(self) -> str:
        """Display label: name if set, otherwise symbol@(x,y)."""
        return self.name or f"{self.symbol}@({self.x},{self.y})"

    @property
    def position(self) -> tuple[float, float]:
        return (self.x, self.y)


@dataclass
class Net(_AutoDirtyMixin):
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
        return (
            f"N {_fmt_num(self.x1)} {_fmt_num(self.y1)}"
            f" {_fmt_num(self.x2)} {_fmt_num(self.y2)} {attrs}"
        )

    @property
    def label(self) -> str | None:
        return self.attributes.get("lab")


@dataclass
class Text(_AutoDirtyMixin):
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
        return (
            f"T {{{self.text}}} {_fmt_num(self.x)} {_fmt_num(self.y)}"
            f" {self.rotation} {self.mirror}"
            f" {_fmt_num(self.xscale)} {_fmt_num(self.yscale)} {attrs}"
        )


@dataclass
class GraphicLine(_AutoDirtyMixin):
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
        return (
            f"L {self.layer} {_fmt_num(self.x1)} {_fmt_num(self.y1)}"
            f" {_fmt_num(self.x2)} {_fmt_num(self.y2)} {attrs}"
        )


@dataclass
class Box(_AutoDirtyMixin):
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
        return (
            f"B {self.layer} {_fmt_num(self.x1)} {_fmt_num(self.y1)}"
            f" {_fmt_num(self.x2)} {_fmt_num(self.y2)} {attrs}"
        )


@dataclass
class Arc(_AutoDirtyMixin):
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
        return (
            f"A {self.layer} {_fmt_num(self.x)} {_fmt_num(self.y)}"
            f" {_fmt_num(self.r)} {_fmt_num(self.start_angle)}"
            f" {_fmt_num(self.sweep_angle)} {attrs}"
        )


@dataclass
class Polygon(_AutoDirtyMixin):
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
