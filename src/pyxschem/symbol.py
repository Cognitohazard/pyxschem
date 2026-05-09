"""Symbol (.sym) file support for xschem.

A Symbol represents a component's interface — its pins, SPICE format
template, default attributes, and graphical representation.

.sym files use the same line format as .sch files. The Symbol class
wraps the parser output and adds pin extraction and metadata access.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pyxschem._base import _ElementContainerMixin
from pyxschem.attributes import parse_attributes
from pyxschem.model import Box, Element, Header, Text
from pyxschem.parser import parse_schematic

# Layer used for pin boxes in xschem .sym files
_PIN_LAYER = 5


@dataclass
class Pin:
    """A symbol pin definition."""

    name: str
    direction: str  # "in", "out", "inout"
    x: float
    y: float


def _resolve_pin(
    pins: list[Pin],
    pin_name: str,
    *,
    case_insensitive: bool = False,
) -> Pin:
    """Find a pin by name, with the same matching rules as
    :func:`pyxschem.generate.get_pin_position` (exact first; in
    ``case_insensitive`` mode, fold case and reject ambiguous matches).
    """
    for p in pins:
        if p.name == pin_name:
            return p
    if case_insensitive:
        target = pin_name.lower()
        matches = [p for p in pins if p.name.lower() == target]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise ValueError(
                f"Pin {pin_name!r} is ambiguous (case-insensitive matches: "
                f"{[p.name for p in matches]})"
            )
    available = [p.name for p in pins]
    raise ValueError(
        f"Pin {pin_name!r} not found on symbol. Available pins: {available}"
    )


class Symbol(_ElementContainerMixin):
    """An xschem symbol — a component's interface definition.

    Usage::

        sym = Symbol.load("devices/res.sym")
        sym.pins        # [Pin(name="P", direction="inout", ...), ...]
        sym.type        # "resistor"
        sym.format      # "@name @pinlist @value m=@m"
        sym.template    # {"name": "R1", "value": "1k", ...}
    """

    def _make_default_header(self, version: str, file_version: str) -> Header:
        return Header.default_symbol(version, file_version)

    def __init__(self, elements: list[Element], path: Path | None = None) -> None:
        self._elements = elements
        self._path = path
        self._k_attrs: dict[str, str] | None = None

    @classmethod
    def load(cls, path: str | Path) -> Symbol:
        """Load a .sym file from disk."""
        p = Path(path)
        text = p.read_text(encoding="utf-8")
        elements = parse_schematic(text)
        return cls(elements, path=p)

    @classmethod
    def from_text(cls, text: str) -> Symbol:
        """Parse a symbol from a string."""
        return cls(parse_schematic(text))

    @classmethod
    def new(cls) -> Symbol:
        """Create a new symbol with a default xschem header."""
        return cls([Header.default_symbol()])

    # -- Properties --

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

    def pin_side(
        self,
        pin_name: str,
        rotation: int = 0,
        mirror: int = 0,
        case_insensitive: bool = False,
    ) -> Literal["left", "right", "up", "down"]:
        """Classify which side of the symbol's body a pin sits on.

        Returns ``"left" | "right" | "up" | "down"`` — the outward
        lead direction in xschem screen coordinates after the given
        ``rotation`` / ``mirror``. Default rotation/mirror gives the
        side relative to the symbol's local frame.
        """
        from pyxschem.geometry import bbox_from_elements, pin_side

        pin = _resolve_pin(self.pins, pin_name, case_insensitive=case_insensitive)
        bbox = bbox_from_elements(self._elements)
        if bbox is None:
            raise ValueError(
                f"Symbol has no graphical extent — cannot classify pin "
                f"{pin_name!r}"
            )
        return pin_side(pin.x, pin.y, bbox, rotation, mirror)

    def add_pin(
        self,
        name: str,
        direction: str,
        x: float,
        y: float,
        size: float = 5,
    ) -> Box:
        """Add a pin box to the symbol and return the underlying Box element."""
        half = size / 2
        item = Box(
            layer=_PIN_LAYER,
            x1=x - half,
            y1=y - half,
            x2=x + half,
            y2=y + half,
            attributes={"name": name, "dir": direction},
        )
        self._elements.append(item)
        return item

    def add_text(
        self,
        text: str,
        x: float,
        y: float,
        rotation: int = 0,
        mirror: int = 0,
        xscale: float = 0.2,
        yscale: float = 0.2,
        attributes: dict[str, str] | None = None,
    ) -> Text:
        """Add a text annotation to the symbol."""
        item = Text(
            text=text,
            x=x,
            y=y,
            rotation=rotation,
            mirror=mirror,
            xscale=xscale,
            yscale=yscale,
            attributes=attributes or {},
        )
        self._elements.append(item)
        return item

    # -- Internal --

    def _get_k_attrs(self) -> dict[str, str]:
        """Parse the K block from header lines."""
        if self._k_attrs is not None:
            return self._k_attrs
        header = self.header
        self._k_attrs = header.k_attributes() if header is not None else {}
        return self._k_attrs
