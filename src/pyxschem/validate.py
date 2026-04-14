"""Schematic validation checks for common design errors.

Provides:
- ``Validator`` — query object that runs checks and caches results
- ``validate()`` — convenience function (creates a Validator internally)
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from pyxschem.model import Element

if TYPE_CHECKING:
    from pyxschem.geometry import GeometryQuery
    from pyxschem.library import SymbolLibrary
    from pyxschem.schematic import Schematic


@dataclass
class ValidationIssue:
    """A single validation finding."""

    severity: Literal["error", "warning"]
    category: Literal[
        "duplicate_name",
        "missing_name",
        "floating_net",
        "unconnected_pin",
        "diagonal_wire",
        "zero_length_net",
        "wire_crosses_body",
        "unintended_junction",
        "pin_collision",
        "component_overlap",
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



class Validator:
    """Validates a schematic for common design errors.

    Usage::

        v = Validator(schematic, libs)
        result = v.validate()
        for issue in result.issues:
            print(issue.severity, issue.message)

    With libs, enables geometry-aware checks (pin connectivity,
    wire-through-body, component overlap, pin collision).
    """

    def __init__(
        self,
        schematic: Schematic,
        libs: SymbolLibrary | None = None,
    ) -> None:
        self._sch = schematic
        self._libs = libs
        self._gq: GeometryQuery | None = None

    def validate(self) -> ValidationResult:
        """Run all applicable validation checks."""
        issues: list[ValidationIssue] = []
        issues.extend(self._check_duplicate_names())
        issues.extend(self._check_missing_names())
        issues.extend(self._check_floating_nets())
        issues.extend(self._check_unintended_junctions())
        if self._libs is not None:
            gq = self._get_geometry_query()
            issues.extend(self._check_unconnected_pins(gq))
            issues.extend(self._check_wire_crosses_body(gq))
            issues.extend(self._check_pin_collisions(gq))
            issues.extend(self._check_component_overlap(gq))
        return ValidationResult(issues=issues)

    def check_net(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        label: str | None = None,
    ) -> list[ValidationIssue]:
        """Inline checks for a net segment (cheap, no libs needed).

        Call before or after add_net to get immediate feedback.
        """
        warnings: list[ValidationIssue] = []
        if x1 != x2 and y1 != y2:
            warnings.append(ValidationIssue(
                severity="warning",
                category="diagonal_wire",
                message=(
                    f"Net ({x1},{y1})-({x2},{y2}) is diagonal"
                    " — xschem wires are typically orthogonal"
                ),
                element=None,
            ))
        if x1 == x2 and y1 == y2 and not label:
            warnings.append(ValidationIssue(
                severity="warning",
                category="zero_length_net",
                message=(
                    f"Zero-length net at ({x1},{y1}) with no label"
                    " — may be unintentional"
                ),
                element=None,
            ))
        return warnings

    # -- internal checks --

    def _get_geometry_query(self) -> GeometryQuery:
        if self._gq is None:
            from pyxschem.geometry import GeometryQuery

            assert self._libs is not None
            self._gq = GeometryQuery(self._sch, self._libs)
        return self._gq

    def _check_duplicate_names(self) -> list[ValidationIssue]:
        by_name: defaultdict[str, list] = defaultdict(list)
        for c in self._sch.components:
            if c.name:
                by_name[c.name].append(c)
        issues = []
        for name, comps in sorted(by_name.items()):
            if len(comps) > 1:
                for c in comps:
                    issues.append(ValidationIssue(
                        severity="error",
                        category="duplicate_name",
                        message=f"Duplicate component name '{name}'",
                        element=c,
                    ))
        return issues

    def _check_missing_names(self) -> list[ValidationIssue]:
        issues = []
        for c in self._sch.components:
            if not c.name:
                issues.append(ValidationIssue(
                    severity="warning",
                    category="missing_name",
                    message=(
                        f"Component with symbol '{c.symbol}'"
                        f" at ({c.x}, {c.y}) has no name"
                    ),
                    element=c,
                ))
        return issues

    def _check_floating_nets(self) -> list[ValidationIssue]:
        comp_positions = {(c.x, c.y) for c in self._sch.components}
        endpoint_count: Counter[tuple[float, float]] = Counter()
        for n in self._sch.nets:
            endpoint_count[(n.x1, n.y1)] += 1
            endpoint_count[(n.x2, n.y2)] += 1

        issues = []
        checked_nets: set[int] = set()
        for n in self._sch.nets:
            net_id = id(n)
            if net_id in checked_nets:
                continue
            for x, y in ((n.x1, n.y1), (n.x2, n.y2)):
                point = (x, y)
                if point in comp_positions:
                    continue
                if endpoint_count[point] >= 2:
                    continue
                checked_nets.add(net_id)
                issues.append(ValidationIssue(
                    severity="warning",
                    category="floating_net",
                    message=(
                        f"Net endpoint ({x}, {y}) is not connected"
                        " to any component or other net"
                    ),
                    element=n,
                ))
                break
        return issues

    def _check_unintended_junctions(self) -> list[ValidationIssue]:
        from pyxschem.geometry import segments_intersect

        issues = []
        nets = self._sch.nets
        for i, a in enumerate(nets):
            for j in range(i + 1, len(nets)):
                b = nets[j]
                pt = segments_intersect(
                    a.x1, a.y1, a.x2, a.y2, b.x1, b.y1, b.x2, b.y2
                )
                if pt is None:
                    continue
                ix, iy = pt
                a_endpoints = {(a.x1, a.y1), (a.x2, a.y2)}
                b_endpoints = {(b.x1, b.y1), (b.x2, b.y2)}
                if (ix, iy) in a_endpoints and (ix, iy) in b_endpoints:
                    continue
                issues.append(ValidationIssue(
                    severity="warning",
                    category="unintended_junction",
                    message=(
                        f"Nets cross at ({ix},{iy}) without a shared endpoint"
                        " — may be an unintended junction"
                    ),
                    element=a,
                ))
        return issues

    def _check_unconnected_pins(
        self, gq: GeometryQuery
    ) -> list[ValidationIssue]:
        net_points: set[tuple[float, float]] = set()
        for n in self._sch.nets:
            net_points.add((n.x1, n.y1))
            net_points.add((n.x2, n.y2))

        issues = []
        for px, py, comp_label, pin_name in gq.pin_positions():
            if (px, py) not in net_points:
                issues.append(ValidationIssue(
                    severity="warning",
                    category="unconnected_pin",
                    message=(
                        f"Pin '{pin_name}' of '{comp_label}'"
                        f" at ({px}, {py}) has no net"
                    ),
                    element=None,
                ))
        return issues

    def _check_wire_crosses_body(
        self, gq: GeometryQuery
    ) -> list[ValidationIssue]:
        from pyxschem.geometry import segment_crosses_bbox

        issues = []
        comp_bboxes = list(gq.component_bboxes().items())

        for net in self._sch.nets:
            endpoints = {(net.x1, net.y1), (net.x2, net.y2)}
            for comp_name, bbox in comp_bboxes:
                if any(bbox.contains_point(x, y) for x, y in endpoints):
                    continue
                if segment_crosses_bbox(net.x1, net.y1, net.x2, net.y2, bbox):
                    issues.append(ValidationIssue(
                        severity="warning",
                        category="wire_crosses_body",
                        message=(
                            f"Net ({net.x1},{net.y1})-({net.x2},{net.y2})"
                            f" passes through component '{comp_name}'"
                        ),
                        element=net,
                    ))
        return issues

    def _check_pin_collisions(
        self, gq: GeometryQuery
    ) -> list[ValidationIssue]:
        from pyxschem.geometry import point_on_segment

        issues = []
        for net in self._sch.nets:
            endpoints = {(net.x1, net.y1), (net.x2, net.y2)}
            for px, py, comp_label, pin_name in gq.pin_positions():
                if (px, py) in endpoints:
                    continue
                if point_on_segment(px, py, net.x1, net.y1, net.x2, net.y2):
                    issues.append(ValidationIssue(
                        severity="warning",
                        category="pin_collision",
                        message=(
                            f"Net ({net.x1},{net.y1})-({net.x2},{net.y2})"
                            f" passes through pin '{pin_name}'"
                            f" of '{comp_label}' at ({px},{py})"
                        ),
                        element=net,
                    ))
        return issues

    def _check_component_overlap(
        self, gq: GeometryQuery
    ) -> list[ValidationIssue]:
        issues = []
        for name_a, name_b in gq.overlapping_components():
            issues.append(ValidationIssue(
                severity="warning",
                category="component_overlap",
                message=(
                    f"Components '{name_a}' and '{name_b}'"
                    " have overlapping bounding boxes"
                ),
                element=None,
            ))
        return issues



def validate(
    schematic: Schematic, libs: SymbolLibrary | None = None
) -> ValidationResult:
    """Run all validation checks on a schematic.

    Convenience wrapper around ``Validator``.
    """
    return Validator(schematic, libs).validate()
