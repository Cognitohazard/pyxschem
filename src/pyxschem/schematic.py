"""High-level Schematic API for xschem .sch files.

Thin facade over parser.py and model.py — provides file I/O,
query methods, and mutation methods.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pyxschem._base import _ElementContainerMixin
from pyxschem.model import Component, Element, Header, Net, Text
from pyxschem.parser import parse_schematic

if TYPE_CHECKING:
    from pyxschem.diff import SchemDiff
    from pyxschem.hierarchy import HierarchyNode
    from pyxschem.library import SymbolLibrary
    from pyxschem.validate import ValidationResult


PortDirection = Literal["in", "out", "inout"]


@dataclass(frozen=True)
class SubcircuitPort:
    """An external port of a sub-schematic (derived from ipin/opin/iopin)."""

    name: str
    direction: PortDirection
    x: float
    y: float


@dataclass(frozen=True)
class BomEntry:
    """Single grouping in a BOM roll-up."""

    symbol: str
    value: str
    footprint: str
    count: int


class Schematic(_ElementContainerMixin):
    """An xschem schematic — the main user-facing object.

    Usage::

        sch = Schematic.load("amplifier.sch")
        r1 = sch.get_component("R1")
        sch.set_component_value("R1", "4.7k")
        sch.save("amplifier_modified.sch")
    """

    def _make_default_header(self, version: str, file_version: str) -> Header:
        return Header.default_schematic(version, file_version)

    def __init__(self, elements: list[Element], path: Path | None = None) -> None:
        self._elements = elements
        self._path = path

    @classmethod
    def load(cls, path: str | Path) -> Schematic:
        """Load a .sch file from disk."""
        p = Path(path)
        text = p.read_text(encoding="utf-8")
        elements = parse_schematic(text)
        return cls(elements, path=p)

    @classmethod
    def from_text(cls, text: str) -> Schematic:
        """Parse a schematic from a string."""
        return cls(parse_schematic(text))

    @classmethod
    def new(cls) -> Schematic:
        """Create a new schematic with a default xschem header."""
        return cls([Header.default_schematic()])

    # -- Properties --

    @property
    def components(self) -> list[Component]:
        return [e for e in self._elements if isinstance(e, Component)]

    @property
    def nets(self) -> list[Net]:
        return [e for e in self._elements if isinstance(e, Net)]

    # -- K-block / subcircuit metadata --

    def k_attributes(self) -> dict[str, str]:
        """Parsed K-block attributes from the header (e.g.
        ``{"type": "subcircuit", "format": "@name @pinlist @symname"}``).

        Returns an empty dict if the schematic has no K block content
        (``K {}`` is the default).
        """
        h = self.header
        if h is None:
            return {}
        return h.k_attributes()

    def subcircuit_ports(self) -> list[SubcircuitPort]:
        """Return ipin/opin/iopin children as ordered ports.

        The list reflects the subcircuit's external port order — same
        order xschem uses when emitting the ``.subckt name PORT1
        PORT2 ...`` header. Coordinates are the original ipin/opin
        positions in the source schematic.

        Symbol references are matched by basename, so both
        ``ipin.sym`` and ``devices/ipin.sym`` are recognised — pyxschem
        elsewhere supports both forms (see :meth:`SymbolLibrary.resolve`)
        and a port-discovery helper that only honoured one would
        silently emit empty port lists for the other.

        Useful for callers stitching this schematic into a parent or
        wiring up a SPICE testbench by name.
        """
        direction_for_symbol: dict[str, PortDirection] = {
            "ipin.sym": "in",
            "opin.sym": "out",
            "iopin.sym": "inout",
        }
        result: list[SubcircuitPort] = []
        for c in self.components:
            basename = Path(c.symbol).name
            d = direction_for_symbol.get(basename)
            if d is None:
                continue
            lab = c.attributes.get("lab")
            if lab is None:
                continue
            result.append(SubcircuitPort(
                name=lab, direction=d, x=c.x, y=c.y,
            ))
        return result

    def set_subcircuit_metadata(
        self,
        *,
        type: str = "subcircuit",
        format: str | None = None,
        template: str | None = None,
        **extra: str,
    ) -> None:
        """Mark this schematic as a subcircuit and set its K-block fields.

        Without ``type=subcircuit`` xschem silently ignores any parent
        ``X``-instance referencing this file. ``format`` controls the
        SPICE expansion (e.g. ``"@name @pinlist @symname"``).
        ``template`` provides default instance attributes. Any extra
        keyword arguments are written verbatim into the K block.

        Existing K-block keys are preserved unless overridden here.
        """
        if self.header is None:
            self._elements.insert(0, Header.default_schematic())
        h = self.header
        assert h is not None
        attrs = h.k_attributes()
        attrs["type"] = type
        if format is not None:
            attrs["format"] = format
        if template is not None:
            attrs["template"] = template
        attrs.update(extra)
        h.set_k_attributes(attrs)

    @property
    def version(self) -> str | None:
        """xschem version string from header (e.g., '3.4.5')."""
        h = self.header
        if h is None:
            return None
        from pyxschem.attributes import parse_attributes

        for line in h.raw_lines:
            if line.startswith("v "):
                # v {xschem version=3.4.5 file_version=1.2}
                return parse_attributes(line[2:]).get("version")
        return None

    # -- Query --

    def get_component(self, name: str) -> Component | None:
        """Find a component by its name attribute."""
        for c in self.components:
            if c.name == name:
                return c
        return None

    def get_components(
        self,
        prefix: str | None = None,
        symbol: str | None = None,
    ) -> list[Component]:
        """Filter components by name prefix and/or symbol path."""
        result = self.components
        if prefix is not None:
            result = [c for c in result if c.name and c.name.startswith(prefix)]
        if symbol is not None:
            result = [c for c in result if c.symbol == symbol]
        return result

    def get_nets(self, label: str | None = None) -> list[Net]:
        """Filter nets by label. Returns all nets if no filter."""
        if label is None:
            return self.nets
        return [n for n in self.nets if n.label == label]

    # -- Mutation --

    def _require_component(self, name: str) -> Component:
        c = self.get_component(name)
        if c is None:
            raise ValueError(f"Component '{name}' not found")
        return c

    def set_component_value(self, name: str, value: str) -> None:
        """Set a component's value attribute by name."""
        self._require_component(name).set_attribute("value", value)

    def set_component_attribute(self, name: str, key: str, value: str) -> None:
        """Set an arbitrary attribute on a component by name."""
        self._require_component(name).set_attribute(key, value)

    def set_component_attributes(self, name: str, **attrs: str) -> None:
        """Set multiple attributes on a component in one call.

        ``sch.set_component_attributes("M1", w="2u", l="0.18u", m="4")``
        is the multi-key form of :meth:`set_component_attribute`.
        """
        c = self._require_component(name)
        for key, value in attrs.items():
            c.set_attribute(key, value)

    def bulk_update(
        self,
        predicate: Callable[[Component], bool],
        mutator: Callable[[Component], None],
    ) -> int:
        """Apply ``mutator`` to every component for which ``predicate`` is true.

        Returns the number of components mutated. The single primitive
        for refactors that don't fit a fixed (symbol → attrs) shape;
        for that shape see :meth:`transform_components`.

        Example::

            sch.bulk_update(
                lambda c: c.symbol == "res.sym" and c.attributes.get("m") is None,
                lambda c: c.set_attribute("m", "1"),
            )
        """
        n = 0
        for c in self.components:
            if predicate(c):
                mutator(c)
                n += 1
        return n

    def transform_components(
        self,
        *,
        symbol: str | None = None,
        prefix: str | None = None,
        attrs: dict[str, str] | None = None,
        attr_remap: dict[str, dict[str, str]] | None = None,
    ) -> int:
        """Bulk-update components matching simple criteria.

        Filters components by ``symbol`` (exact path) and/or ``prefix``
        (component-name prefix), then applies:

        * ``attrs``: set each ``key=value`` literally on every match.
        * ``attr_remap``: per-attribute value rewrite.  Keys are
          attribute names; values are ``{old_value: new_value}`` maps.
          Unknown current values are left alone.

        Returns the number of components whose attributes *actually*
        changed — matches that were no-ops (e.g. an ``attr_remap``
        whose table missed every current value) are not counted.

        Example::

            sch.transform_components(
                symbol="nmos4.sym",
                attr_remap={"model": {"n": "nmos_lvt"}},
            )
        """
        if not attrs and not attr_remap:
            return 0

        def matches(c: Component) -> bool:
            if symbol is not None and c.symbol != symbol:
                return False
            if prefix is not None and not (c.name and c.name.startswith(prefix)):
                return False
            return True

        n_changed = 0
        for c in self.components:
            if not matches(c):
                continue
            before = dict(c.attributes)
            if attrs:
                for k, v in attrs.items():
                    c.set_attribute(k, v)
            if attr_remap:
                for key, table in attr_remap.items():
                    cur = c.attributes.get(key)
                    if cur is not None and cur in table:
                        c.set_attribute(key, table[cur])
            if dict(c.attributes) != before:
                n_changed += 1
        return n_changed

    def bom(
        self,
        libs: SymbolLibrary | None = None,
        *,
        flatten: bool = False,
        ignore_symbols: set[str] | None = None,
    ) -> list[BomEntry]:
        """Roll up components into a bill-of-materials.

        Groups by ``(symbol, value, footprint)`` and returns a list of
        :class:`BomEntry` sorted by symbol then value. Pure-electrical
        helper symbols (lab_pin, gnd, vdd, ipin, opin, title, …) are
        excluded by default — pass ``ignore_symbols`` to override.

        Args:
            libs: Required when ``flatten=True`` — used to descend
                into sub-schematics.
            flatten: If true, walk the design hierarchy and roll up
                leaf components only.
            ignore_symbols: Override the default skip list.

        Returns:
            Sorted list of :class:`BomEntry`.
        """
        if ignore_symbols is None:
            ignore_symbols = {
                "lab_pin.sym", "gnd.sym", "vdd.sym",
                "ipin.sym", "opin.sym", "iopin.sym",
                "title.sym", "launcher.sym", "code.sym",
                "code_shown.sym", "noconn.sym",
            }

        def comp_iter() -> "list[Component]":
            if not flatten:
                return list(self.components)
            if libs is None:
                raise ValueError("flatten=True requires libs=")
            leaves: list[Component] = []
            for node in self.flatten(libs):
                if node.component is not None:
                    leaves.append(node.component)
            return leaves

        bucket: Counter[tuple[str, str, str]] = Counter()
        for c in comp_iter():
            if c.symbol in ignore_symbols:
                continue
            value = c.attributes.get("value", "") or ""
            footprint = c.attributes.get("footprint", "") or ""
            bucket[(c.symbol, value, footprint)] += 1

        return [
            BomEntry(symbol=s, value=v, footprint=f, count=n)
            for (s, v, f), n in sorted(bucket.items())
        ]

    def remove_component(self, name: str) -> None:
        """Remove a component by name."""
        self._elements.remove(self._require_component(name))

    def remove_net(self, net: Net) -> None:
        """Remove a net by object identity."""
        try:
            self._elements.remove(net)
        except ValueError:
            raise ValueError("Net not found in schematic") from None

    def remove_text(self, text: Text) -> None:
        """Remove a text element by object identity."""
        try:
            self._elements.remove(text)
        except ValueError:
            raise ValueError("Text not found in schematic") from None

    def add_component(
        self,
        symbol: str,
        x: float,
        y: float,
        rotation: int = 0,
        mirror: int = 0,
        attributes: dict[str, str] | None = None,
    ) -> Component:
        """Add a new component to the schematic."""
        comp = Component(
            symbol=symbol,
            x=x,
            y=y,
            rotation=rotation,
            mirror=mirror,
            attributes=attributes or {},
        )
        self._elements.append(comp)
        return comp

    def add_net(
        self,
        x1: float | None = None,
        y1: float | None = None,
        x2: float | None = None,
        y2: float | None = None,
        label: str | None = None,
        *,
        between: tuple[tuple[str, str], tuple[str, str]] | None = None,
        libs: SymbolLibrary | None = None,
        case_insensitive: bool = False,
    ) -> Net:
        """Add a net (wire) segment to the schematic.

        Two call forms:

        * **Coordinates** (the original): ``add_net(x1, y1, x2, y2)``.
        * **Pin endpoints**: ``add_net(between=(("R1","P"),("C1","p")),
          libs=L)`` resolves both pin coordinates through ``libs`` and
          lays the segment. Pins must be orthogonally aligned;
          ``ValueError`` otherwise. xschem itself is happy to draw a
          diagonal wire, but pyxschem refuses by default because
          (a) xschem's validator warns on it, and (b) most diagonal
          requests are mistakes by callers who didn't realise the
          two pins disagree on rotation. If you genuinely want a
          diagonal segment, use the four-coordinate form. This is
          also the path used by :meth:`add_wire` (which is now a
          thin alias).

        ``label`` and ``case_insensitive`` apply to either form.
        """
        if between is not None:
            if libs is None:
                raise ValueError("add_net(between=...) requires libs=")
            if any(v is not None for v in (x1, y1, x2, y2)):
                raise ValueError(
                    "add_net: pass either coordinates or between=, not both"
                )
            (ca, pa), (cb, pb) = between
            x1, y1 = self.pin_position(
                ca, pa, libs, case_insensitive=case_insensitive
            )
            x2, y2 = self.pin_position(
                cb, pb, libs, case_insensitive=case_insensitive
            )
            if x1 != x2 and y1 != y2:
                raise ValueError(
                    f"Pins are not orthogonally aligned: "
                    f"{ca}.{pa}={x1, y1} vs {cb}.{pb}={x2, y2}. "
                    "xschem wires must be horizontal or vertical."
                )
        elif None in (x1, y1, x2, y2):
            raise ValueError(
                "add_net: must pass all four coordinates or between=("
                "(compA,pinA),(compB,pinB))"
            )

        assert x1 is not None and y1 is not None
        assert x2 is not None and y2 is not None
        attrs = {"lab": label} if label else {}
        net = Net(x1=x1, y1=y1, x2=x2, y2=y2, attributes=attrs)
        self._elements.append(net)
        return net

    def add_text(
        self,
        text: str,
        x: float,
        y: float,
        rotation: int = 0,
        mirror: int = 0,
        xscale: float = 0.4,
        yscale: float = 0.4,
        attributes: dict[str, str] | None = None,
    ) -> Text:
        """Add a text annotation to the schematic."""
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

    # -- Generation --

    def pin_position(
        self,
        comp_name: str,
        pin_name: str,
        libs: SymbolLibrary,
        *,
        case_insensitive: bool = False,
    ) -> tuple[float, float]:
        """Get a component pin's position in schematic coordinates.

        Args:
            comp_name: Component name (e.g., "R1").
            pin_name: Pin name (e.g., "P").
            libs: Symbol library for resolving the component's symbol.
            case_insensitive: If true, fold pin-name case during the
                lookup. Useful because the stock xschem device library
                mixes ``P/M`` (resistor) with ``p/m`` (capa, vsource).

        Returns:
            (x, y) in schematic coordinates.
        """
        from pyxschem.generate import get_pin_position

        comp = self.get_component(comp_name)
        if comp is None:
            raise ValueError(f"Component '{comp_name}' not found")
        return get_pin_position(
            comp, pin_name, libs, case_insensitive=case_insensitive
        )

    def pin_side(
        self,
        comp_name: str,
        pin_name: str,
        libs: SymbolLibrary,
        *,
        case_insensitive: bool = False,
    ) -> Literal["left", "right", "up", "down"]:
        """Classify which side of the placed bounding box a pin sits
        on. Returns ``"left" | "right" | "up" | "down"`` accounting
        for the component's rotation and mirror.
        """
        comp = self._require_component(comp_name)
        sym = libs.resolve(comp.symbol)
        if sym is None:
            raise ValueError(
                f"Cannot resolve symbol {comp.symbol!r} for component "
                f"{comp_name!r}"
            )
        return sym.pin_side(
            pin_name,
            rotation=comp.rotation,
            mirror=comp.mirror,
            case_insensitive=case_insensitive,
        )

    def connect(
        self,
        comp_name: str,
        pin_name: str,
        label: str,
        libs: SymbolLibrary,
        *,
        case_insensitive: bool = False,
    ) -> Component:
        """Tag a component pin with a net label.

        Places a ``lab_pin.sym`` at the pin coordinate so xschem's
        netlister emits the requested label as the node name. Returns
        the created lab_pin component.
        """
        from pyxschem.generate import connect_pin

        return connect_pin(
            self, comp_name, pin_name, label, libs,
            case_insensitive=case_insensitive,
        )

    #: Synonym for :meth:`connect`.
    add_label_pin = connect

    def add_wire(
        self,
        comp_a: str,
        pin_a: str,
        comp_b: str,
        pin_b: str,
        libs: SymbolLibrary,
        *,
        case_insensitive: bool = False,
    ) -> Net:
        """Draw an orthogonal wire between two component pins.

        Thin alias of :meth:`add_net` with ``between=...``: computes
        both pin coordinates through ``libs`` and lays the segment.
        Raises ``ValueError`` if the pins are not on a shared
        horizontal or vertical axis.
        """
        return self.add_net(
            between=((comp_a, pin_a), (comp_b, pin_b)),
            libs=libs,
            case_insensitive=case_insensitive,
        )

    # -- Hierarchy --

    def hierarchy(self, libs: SymbolLibrary) -> list[HierarchyNode]:
        """Walk the design hierarchy tree.

        Args:
            libs: Symbol library for resolving subcircuit references.

        Returns:
            List of top-level HierarchyNode instances.
        """
        from pyxschem.hierarchy import walk_hierarchy

        return walk_hierarchy(self, libs)

    def find_all(
        self,
        libs: SymbolLibrary,
        prefix: str | None = None,
        symbol: str | None = None,
    ) -> list[HierarchyNode]:
        """Find components across the full hierarchy.

        Args:
            libs: Symbol library for resolving subcircuit references.
            prefix: Filter by component name prefix.
            symbol: Filter by symbol path substring.
        """
        from pyxschem.hierarchy import find_all

        return find_all(self, libs, prefix=prefix, symbol=symbol)

    def flatten(self, libs: SymbolLibrary) -> list[HierarchyNode]:
        """Flatten hierarchy into all leaf (primitive) components."""
        from pyxschem.hierarchy import flatten

        return flatten(self, libs)

    # -- Diffing --

    def diff(self, other: Schematic) -> SchemDiff:
        """Compare this schematic to another and return differences.

        Args:
            other: The schematic to compare against.

        Returns:
            A SchemDiff describing all changes.
        """
        from pyxschem.diff import diff_schematics

        return diff_schematics(self, other)

    # -- Validation --

    def validate(self, libs: SymbolLibrary | None = None) -> ValidationResult:
        """Run validation checks on this schematic.

        Args:
            libs: Optional symbol library for pin-level checks.

        Returns:
            ValidationResult with all found issues.
        """
        from pyxschem.validate import validate as _validate

        return _validate(self, libs=libs)
