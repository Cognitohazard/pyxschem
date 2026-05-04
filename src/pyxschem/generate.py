"""Generation helpers for programmatic schematic construction.

Provides pin-position geometry transforms, pin labelling, and wiring
convenience for building schematics from code.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pyxschem.geometry import transform_point

if TYPE_CHECKING:
    from pyxschem.library import SymbolLibrary
    from pyxschem.model import Component
    from pyxschem.schematic import Schematic


# Re-export for backwards compatibility — validate.py imports this.
transform_pin = transform_point

# xschem propagates a net name only via symbols whose K block sets
# ``net_name=true`` (lab_pin / gnd / vdd / ipin / opin). Try the
# basename form first so the emitted reference is what xschem itself
# will most reliably resolve via XSCHEM_LIBRARY_PATH; fall back to the
# subpath form for libraries rooted above the devices directory.
_LABEL_PIN_CANDIDATES: tuple[str, ...] = ("lab_pin.sym", "devices/lab_pin.sym")


def get_pin_position(
    component: Component,
    pin_name: str,
    libs: SymbolLibrary,
    *,
    case_insensitive: bool = False,
) -> tuple[float, float]:
    """Get a component pin's position in schematic coordinates.

    Args:
        component: The component instance.
        pin_name: Name of the pin (e.g., "P", "d", "g"). Case-sensitive
            by default — xschem ships symbols with a mix of upper- and
            lower-case pin names (``res.sym`` → ``P/M``, ``capa.sym`` →
            ``p/m``). Set ``case_insensitive=True`` to fold the
            difference. The error message always suggests a unique
            case-insensitive match if one exists.
        libs: Symbol library for resolving the component's symbol.
        case_insensitive: If true, match pin names without regard to
            case. Raises ``ValueError`` if the lookup is ambiguous.

    Returns:
        (x, y) in schematic coordinates.

    Raises:
        ValueError: If symbol cannot be resolved or pin not found.
    """
    sym = libs.resolve(component.symbol)
    if sym is None:
        raise ValueError(
            f"Cannot resolve symbol '{component.symbol}'"
            f" for component '{component.name}'"
        )

    if case_insensitive:
        target = pin_name.lower()
        matches = [p for p in sym.pins if p.name.lower() == target]
        if len(matches) == 1:
            pin = matches[0]
            return transform_pin(
                pin.x, pin.y, component.x, component.y,
                component.rotation, component.mirror,
            )
        if len(matches) > 1:
            raise ValueError(
                f"Pin '{pin_name}' is ambiguous on symbol "
                f"'{component.symbol}' (case-insensitive matches: "
                f"{[p.name for p in matches]})"
            )
    else:
        for pin in sym.pins:
            if pin.name == pin_name:
                return transform_pin(
                    pin.x,
                    pin.y,
                    component.x,
                    component.y,
                    component.rotation,
                    component.mirror,
                )

    available = [p.name for p in sym.pins]
    suggestion = ""
    case_match = next(
        (p.name for p in sym.pins if p.name.lower() == pin_name.lower()),
        None,
    )
    if case_match is not None and case_match != pin_name:
        suggestion = (
            f" (did you mean '{case_match}'?"
            f" — or pass case_insensitive=True)"
        )
    raise ValueError(
        f"Pin '{pin_name}' not found on symbol '{component.symbol}'"
        f" (component '{component.name}', rotation={component.rotation},"
        f" mirror={component.mirror}).{suggestion}"
        f" Available pins: {available}"
    )


def connect_pin(
    schematic: Schematic,
    comp_name: str,
    pin_name: str,
    label: str,
    libs: SymbolLibrary,
    *,
    case_insensitive: bool = False,
) -> Component:
    """Tag a component pin with a net label by placing a lab_pin.

    xschem propagates net names only via symbols whose K block sets
    ``net_name=true`` (lab_pin / gnd / vdd / ipin / opin). This helper
    drops a ``lab_pin.sym`` at the target pin's coordinate so the
    netlister adopts the requested label.

    Args:
        schematic: The schematic to modify.
        comp_name: Component name (e.g., "R1").
        pin_name: Pin name (e.g., "P").
        label: Net label (e.g., "VDD").
        libs: Symbol library for resolving symbols.

    Returns:
        The created lab_pin Component.

    Raises:
        ValueError: If component not found, symbol unresolvable, or pin
            missing.
    """
    comp = schematic.get_component(comp_name)
    if comp is None:
        raise ValueError(f"Component '{comp_name}' not found")

    px, py = get_pin_position(
        comp, pin_name, libs, case_insensitive=case_insensitive
    )
    label_symbol = next(
        (ref for ref in _LABEL_PIN_CANDIDATES if libs.resolve(ref) is not None),
        None,
    )
    if label_symbol is None:
        raise ValueError(
            "Cannot resolve a lab_pin symbol through the supplied "
            f"SymbolLibrary; tried {list(_LABEL_PIN_CANDIDATES)}."
        )
    name = _next_label_pin_name(schematic)
    return schematic.add_component(
        label_symbol,
        x=px,
        y=py,
        attributes={"name": name, "lab": label},
    )


def _next_label_pin_name(schematic: Schematic) -> str:
    """Pick a fresh `lp_<n>` name not already used in the schematic."""
    used = {c.name for c in schematic.components if c.name}
    i = 1
    while f"lp_{i}" in used:
        i += 1
    return f"lp_{i}"
