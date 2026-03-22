"""Symbol (.sym) file support for xschem.

A Symbol represents a component's interface — its pins, SPICE format
template, default attributes, and graphical representation.

.sym files use the same line format as .sch files. The Symbol class
wraps the parser output and adds pin extraction and metadata access.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pyxschem.attributes import parse_attributes
from pyxschem.model import Box, Element, Header
from pyxschem.parser import parse_schematic, serialize_schematic

# Layer used for pin boxes in xschem .sym files
_PIN_LAYER = 5


@dataclass
class Pin:
    """A symbol pin definition."""

    name: str
    direction: str  # "in", "out", "inout"
    x: float
    y: float


class Symbol:
    """An xschem symbol — a component's interface definition.

    Usage::

        sym = Symbol.load("devices/res.sym")
        sym.pins        # [Pin(name="P", direction="inout", ...), ...]
        sym.type        # "resistor"
        sym.format      # "@name @pinlist @value m=@m"
        sym.template    # {"name": "R1", "value": "1k", ...}
    """

    def __init__(self, elements: list[Element], path: Path | None = None) -> None:
        self._elements = elements
        self._path = path
        self._k_attrs: dict[str, str] | None = None

    @classmethod
    def load(cls, path: str | Path) -> Symbol:
        """Load a .sym file from disk."""
        p = Path(path)
        text = p.read_text()
        elements = parse_schematic(text)
        return cls(elements, path=p)

    @classmethod
    def from_text(cls, text: str) -> Symbol:
        """Parse a symbol from a string."""
        return cls(parse_schematic(text))

    # -- Properties --

    @property
    def header(self) -> Header | None:
        for e in self._elements:
            if isinstance(e, Header):
                return e
        return None

    @property
    def pins(self) -> list[Pin]:
        """Extract pins from layer-5 Box elements with name attribute."""
        result = []
        for e in self._elements:
            if isinstance(e, Box) and e.layer == _PIN_LAYER and "name" in e.attributes:
                cx = (e.x1 + e.x2) / 2
                cy = (e.y1 + e.y2) / 2
                result.append(
                    Pin(
                        name=e.attributes["name"],
                        direction=e.attributes.get("dir", "inout"),
                        x=cx,
                        y=cy,
                    )
                )
        return result

    @property
    def type(self) -> str | None:
        """Component type from K block (e.g., 'resistor', 'nmos')."""
        return self._get_k_attrs().get("type")

    @property
    def format(self) -> str | None:
        """SPICE netlist format template from K block."""
        return self._get_k_attrs().get("format")

    @property
    def template(self) -> dict[str, str]:
        """Default instance attributes from K block template field."""
        raw = self._get_k_attrs().get("template", "")
        if not raw:
            return {}
        return parse_attributes(raw)

    # -- I/O --

    def to_text(self) -> str:
        """Serialize the symbol to a string."""
        return serialize_schematic(self._elements)

    # -- Internal --

    def _get_k_attrs(self) -> dict[str, str]:
        """Parse the K block from header lines."""
        if self._k_attrs is not None:
            return self._k_attrs

        self._k_attrs = {}
        header = self.header
        if header is None:
            return self._k_attrs

        for line in header.raw_lines:
            if line.startswith("K "):
                # K {content...} — extract the braced content
                brace_start = line.index("{")
                content = line[brace_start + 1 :]
                # Find matching close brace
                if content.endswith("}"):
                    content = content[:-1]
                self._k_attrs = parse_attributes(content)
                break

        return self._k_attrs
