"""High-level Schematic API for xschem .sch files.

Thin facade over parser.py and model.py — provides file I/O,
query methods, and mutation methods.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from pyxschem.model import Component, Element, Header, Net, Text
from pyxschem.parser import parse_schematic, serialize_schematic

if TYPE_CHECKING:
    from pyxschem.diff import SchemDiff
    from pyxschem.hierarchy import HierarchyNode
    from pyxschem.library import SymbolLibrary
    from pyxschem.validate import ValidationResult


class Schematic:
    """An xschem schematic — the main user-facing object.

    Usage::

        sch = Schematic.load("amplifier.sch")
        r1 = sch.get_component("R1")
        sch.set_component_value("R1", "4.7k")
        sch.save("amplifier_modified.sch")
    """

    def __init__(self, elements: list[Element], path: Path | None = None) -> None:
        self._elements = elements
        self._path = path

    @classmethod
    def load(cls, path: str | Path) -> Schematic:
        """Load a .sch file from disk."""
        p = Path(path)
        text = p.read_text()
        elements = parse_schematic(text)
        return cls(elements, path=p)

    @classmethod
    def from_text(cls, text: str) -> Schematic:
        """Parse a schematic from a string."""
        return cls(parse_schematic(text))

    @classmethod
    def new(cls) -> Schematic:
        """Create an empty schematic."""
        return cls([])

    # -- Properties --

    @property
    def components(self) -> list[Component]:
        return [e for e in self._elements if isinstance(e, Component)]

    @property
    def nets(self) -> list[Net]:
        return [e for e in self._elements if isinstance(e, Net)]

    @property
    def texts(self) -> list[Text]:
        return [e for e in self._elements if isinstance(e, Text)]

    @property
    def header(self) -> Header | None:
        for e in self._elements:
            if isinstance(e, Header):
                return e
        return None

    @property
    def version(self) -> str | None:
        """xschem version string from header (e.g., '3.4.5')."""
        h = self.header
        if h is None:
            return None
        for line in h.raw_lines:
            if line.startswith("v "):
                # v {xschem version=3.4.5 file_version=1.2}
                from pyxschem.attributes import parse_attributes

                attrs = parse_attributes(line[2:])
                return attrs.get("version")

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

    def set_component_value(self, name: str, value: str) -> None:
        """Set a component's value attribute by name."""
        c = self.get_component(name)
        if c is None:
            raise ValueError(f"Component '{name}' not found")
        c.set_attribute("value", value)

    def set_component_attribute(self, name: str, key: str, value: str) -> None:
        """Set an arbitrary attribute on a component by name."""
        c = self.get_component(name)
        if c is None:
            raise ValueError(f"Component '{name}' not found")
        c.set_attribute(key, value)

    def remove_component(self, name: str) -> None:
        """Remove a component by name."""
        c = self.get_component(name)
        if c is None:
            raise ValueError(f"Component '{name}' not found")
        self._elements.remove(c)

    def add_component(
        self,
        symbol: str,
        x: int,
        y: int,
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
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        label: str | None = None,
    ) -> Net:
        """Add a net (wire) segment to the schematic.

        Args:
            x1, y1, x2, y2: Net endpoint coordinates.
            label: Optional net label (creates lab= attribute).

        Returns:
            The created Net.
        """
        attrs = {"lab": label} if label else {}
        net = Net(x1=x1, y1=y1, x2=x2, y2=y2, attributes=attrs)
        self._elements.append(net)
        return net

    # -- Generation --

    def pin_position(
        self,
        comp_name: str,
        pin_name: str,
        libs: SymbolLibrary,
    ) -> tuple[float, float]:
        """Get a component pin's position in schematic coordinates.

        Args:
            comp_name: Component name (e.g., "R1").
            pin_name: Pin name (e.g., "P").
            libs: Symbol library for resolving the component's symbol.

        Returns:
            (x, y) in schematic coordinates.
        """
        from pyxschem.generate import get_pin_position

        comp = self.get_component(comp_name)
        if comp is None:
            raise ValueError(f"Component '{comp_name}' not found")
        return get_pin_position(comp, pin_name, libs)

    def connect(
        self,
        comp_name: str,
        pin_name: str,
        label: str,
        libs: SymbolLibrary,
    ) -> Net:
        """Connect a component's pin to a labeled net.

        Creates a net segment at the pin position with the given label.

        Args:
            comp_name: Component name (e.g., "R1").
            pin_name: Pin name (e.g., "P").
            label: Net label (e.g., "VDD").
            libs: Symbol library for resolving symbols.

        Returns:
            The created Net.
        """
        from pyxschem.generate import connect_pin

        return connect_pin(self, comp_name, pin_name, label, libs)

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

    # -- I/O --

    def to_text(self) -> str:
        """Serialize the schematic to a string."""
        return serialize_schematic(self._elements)

    def save(self, path: str | Path | None = None) -> None:
        """Write the schematic to a file.

        Args:
            path: Output path. If None, uses the original load path.
        """
        if path is not None:
            p = Path(path)
        elif self._path is not None:
            p = self._path
        else:
            raise ValueError(
                "No path specified and schematic was not loaded from a file"
            )
        p.write_text(self.to_text())
