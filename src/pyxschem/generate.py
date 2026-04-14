"""Generation helpers for programmatic schematic construction.

Provides pin-position geometry transforms and wiring convenience
for building schematics from code.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pyxschem.geometry import transform_point

if TYPE_CHECKING:
    from pyxschem.library import SymbolLibrary
    from pyxschem.model import Component, Net
    from pyxschem.schematic import Schematic


# Re-export for backwards compatibility — validate.py imports this.
transform_pin = transform_point


def get_pin_position(
    component: Component,
    pin_name: str,
    libs: SymbolLibrary,
) -> tuple[float, float]:
    """Get a component pin's position in schematic coordinates.

    Args:
        component: The component instance.
        pin_name: Name of the pin (e.g., "P", "d", "g").
        libs: Symbol library for resolving the component's symbol.

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
    raise ValueError(
        f"Pin '{pin_name}' not found on symbol '{component.symbol}'. "
        f"Available pins: {available}"
    )


def connect_pin(
    schematic: Schematic,
    comp_name: str,
    pin_name: str,
    label: str,
    libs: SymbolLibrary,
) -> Net:
    """Connect a component's pin to a labeled net.

    Creates a zero-length Net segment at the pin position with the
    given label. In xschem, nets with the same label are electrically
    connected.

    Args:
        schematic: The schematic to modify.
        comp_name: Component name (e.g., "R1").
        pin_name: Pin name (e.g., "P").
        label: Net label (e.g., "VDD").
        libs: Symbol library for resolving symbols.

    Returns:
        The created Net.

    Raises:
        ValueError: If component not found, symbol unresolvable, or pin missing.
    """
    comp = schematic.get_component(comp_name)
    if comp is None:
        raise ValueError(f"Component '{comp_name}' not found")

    px, py = get_pin_position(comp, pin_name, libs)

    return schematic.add_net(x1=px, y1=py, x2=px, y2=py, label=label)
