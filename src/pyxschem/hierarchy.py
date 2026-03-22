"""Hierarchy traversal for xschem designs.

Walks subcircuit trees by recursively loading sub-schematics
via SymbolLibrary resolution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyxschem.library import SymbolLibrary
    from pyxschem.model import Component
    from pyxschem.schematic import Schematic


@dataclass
class HierarchyNode:
    """A node in the design hierarchy tree."""

    path: str
    component: Component
    symbol_path: str
    is_subcircuit: bool
    children: list[HierarchyNode] = field(default_factory=list)
    schematic: Schematic | None = None


def walk_hierarchy(
    sch: Schematic,
    libs: SymbolLibrary,
    prefix: str = "",
) -> list[HierarchyNode]:
    """Walk the design hierarchy tree.

    For each component, checks if its symbol references a .sch file
    (subcircuit). If so, recursively loads and walks that schematic.

    Args:
        sch: Top-level schematic.
        libs: Symbol library for resolving references.
        prefix: Instance path prefix (for recursion).

    Returns:
        List of top-level HierarchyNode instances.
    """
    nodes: list[HierarchyNode] = []

    for comp in sch.components:
        name = comp.name or comp.symbol
        path = f"{prefix}.{name}" if prefix else name

        # Check if this is a subcircuit (.sch reference)
        sub_sch = _resolve_subcircuit(comp.symbol, libs)

        if sub_sch is not None:
            children = walk_hierarchy(sub_sch, libs, prefix=path)
            nodes.append(
                HierarchyNode(
                    path=path,
                    component=comp,
                    symbol_path=comp.symbol,
                    is_subcircuit=True,
                    children=children,
                    schematic=sub_sch,
                )
            )
        else:
            nodes.append(
                HierarchyNode(
                    path=path,
                    component=comp,
                    symbol_path=comp.symbol,
                    is_subcircuit=False,
                )
            )

    return nodes


def find_all(
    sch: Schematic,
    libs: SymbolLibrary,
    prefix: str | None = None,
    symbol: str | None = None,
) -> list[HierarchyNode]:
    """Find components across the full hierarchy.

    Args:
        sch: Top-level schematic.
        libs: Symbol library for resolving references.
        prefix: Filter by component name prefix (e.g., "M" for MOSFETs).
        symbol: Filter by symbol path substring (e.g., "nmos").

    Returns:
        Flat list of matching leaf nodes with full instance paths.
    """
    all_nodes = _collect_leaves(walk_hierarchy(sch, libs))
    results: list[HierarchyNode] = []

    for node in all_nodes:
        name = node.component.name or ""
        if prefix is not None and not name.startswith(prefix):
            continue
        if symbol is not None and symbol not in node.symbol_path:
            continue
        results.append(node)

    return results


def flatten(sch: Schematic, libs: SymbolLibrary) -> list[HierarchyNode]:
    """Flatten hierarchy into a list of all leaf (primitive) components.

    Args:
        sch: Top-level schematic.
        libs: Symbol library for resolving references.

    Returns:
        Flat list of all leaf nodes with full instance paths.
    """
    return _collect_leaves(walk_hierarchy(sch, libs))


def _collect_leaves(nodes: list[HierarchyNode]) -> list[HierarchyNode]:
    """Recursively collect all leaf nodes from a hierarchy tree."""
    result: list[HierarchyNode] = []
    for node in nodes:
        if node.is_subcircuit:
            result.extend(_collect_leaves(node.children))
        else:
            result.append(node)
    return result


def _resolve_subcircuit(
    symbol_ref: str,
    libs: SymbolLibrary,
) -> Schematic | None:
    """Try to resolve a symbol reference as a subcircuit (.sch file).

    Returns loaded Schematic if the reference is a .sch, None otherwise.
    """
    from pyxschem.schematic import Schematic as Sch

    # Direct .sch reference
    if symbol_ref.endswith(".sch"):
        for base in libs._paths:
            candidate = base / symbol_ref
            if candidate.is_file():
                return Sch.load(candidate)
        return None

    # Try adding .sch extension
    sch_ref = symbol_ref + ".sch"
    for base in libs._paths:
        candidate = base / sch_ref
        if candidate.is_file():
            return Sch.load(candidate)

    # It's a .sym or unresolvable — leaf node
    return None
