"""Schematic validation checks for common design errors.

Checks for duplicate names, missing names, floating nets,
and unconnected pins.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from pyxschem.model import Element

if TYPE_CHECKING:
    from pyxschem.library import SymbolLibrary
    from pyxschem.schematic import Schematic


def _net_endpoint_set(sch: Schematic) -> set[tuple[float, float]]:
    """Collect all net endpoint positions in the schematic."""
    points: set[tuple[float, float]] = set()
    for n in sch.nets:
        points.add((n.x1, n.y1))
        points.add((n.x2, n.y2))
    return points


@dataclass
class ValidationIssue:
    """A single validation finding."""

    severity: Literal["error", "warning"]
    category: Literal[
        "duplicate_name", "missing_name", "floating_net", "unconnected_pin"
    ]
    message: str
    element: Element | None


@dataclass
class ValidationResult:
    """Aggregated validation results."""

    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """True if there are no errors (warnings are acceptable)."""
        return all(i.severity != "error" for i in self.issues)


def _check_duplicate_names(sch: Schematic) -> list[ValidationIssue]:
    """Find components sharing the same name."""
    by_name: defaultdict[str, list] = defaultdict(list)
    for c in sch.components:
        if c.name:
            by_name[c.name].append(c)
    issues = []
    for name, comps in sorted(by_name.items()):
        if len(comps) > 1:
            for c in comps:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        category="duplicate_name",
                        message=f"Duplicate component name '{name}'",
                        element=c,
                    )
                )
    return issues


def _check_missing_names(sch: Schematic) -> list[ValidationIssue]:
    """Find components with no name attribute."""
    issues = []
    for c in sch.components:
        if not c.name:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    category="missing_name",
                    message=(
                        f"Component with symbol '{c.symbol}'"
                        f" at ({c.x}, {c.y}) has no name"
                    ),
                    element=c,
                )
            )
    return issues


def _check_floating_nets(sch: Schematic) -> list[ValidationIssue]:
    """Find net endpoints not touching any component or other net endpoint."""
    comp_positions = {(c.x, c.y) for c in sch.components}

    # Count how many nets contribute each endpoint
    endpoint_count: Counter[tuple[float, float]] = Counter()
    for n in sch.nets:
        endpoint_count[(n.x1, n.y1)] += 1
        endpoint_count[(n.x2, n.y2)] += 1

    issues = []
    checked_nets: set[int] = set()
    for n in sch.nets:
        net_id = id(n)
        if net_id in checked_nets:
            continue
        for x, y in ((n.x1, n.y1), (n.x2, n.y2)):
            point = (x, y)
            if point in comp_positions:
                continue
            # Connected if another net also has this endpoint
            if endpoint_count[point] >= 2:
                continue
            checked_nets.add(net_id)
            issues.append(
                ValidationIssue(
                    severity="warning",
                    category="floating_net",
                    message=(
                        f"Net endpoint ({x}, {y}) is not connected"
                        " to any component or other net"
                    ),
                    element=n,
                )
            )
            break
    return issues


def _check_unconnected_pins(
    sch: Schematic, libs: SymbolLibrary
) -> list[ValidationIssue]:
    """Find component pins without a net endpoint at their position."""
    from pyxschem.generate import transform_pin

    net_points = _net_endpoint_set(sch)

    issues = []
    for comp in sch.components:
        sym = libs.resolve(comp.symbol)
        if sym is None:
            continue
        for pin in sym.pins:
            px, py = transform_pin(
                pin.x, pin.y, comp.x, comp.y, comp.rotation, comp.mirror
            )
            if (px, py) not in net_points:
                comp_label = comp.name or f"{comp.symbol}@({comp.x},{comp.y})"
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        category="unconnected_pin",
                        message=(
                            f"Pin '{pin.name}' of '{comp_label}'"
                            f" at ({px}, {py}) has no net"
                        ),
                        element=comp,
                    )
                )
    return issues


def validate(
    schematic: Schematic, libs: SymbolLibrary | None = None
) -> ValidationResult:
    """Run all validation checks on a schematic.

    Args:
        schematic: The schematic to validate.
        libs: Optional symbol library. When provided, enables
              pin-level connectivity checks.

    Returns:
        ValidationResult with all found issues.
    """
    issues: list[ValidationIssue] = []
    issues.extend(_check_duplicate_names(schematic))
    issues.extend(_check_missing_names(schematic))
    issues.extend(_check_floating_nets(schematic))
    if libs is not None:
        issues.extend(_check_unconnected_pins(schematic, libs))
    return ValidationResult(issues=issues)
