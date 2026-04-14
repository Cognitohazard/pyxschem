"""Geometric primitives and spatial queries for schematic layout.

Provides:
- ``BBox`` — axis-aligned bounding box dataclass
- Coordinate transforms (``transform_point``, ``transform_bbox``)
- Segment intersection utilities
- ``GeometryQuery`` — spatial analyzer for a schematic + symbol library
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pyxschem.model import Arc, Box, Element, GraphicLine, Polygon

if TYPE_CHECKING:
    from pyxschem.library import SymbolLibrary
    from pyxschem.schematic import Schematic
    from pyxschem.symbol import Symbol

# Layer used for pin boxes — excluded from symbol bounding boxes
_PIN_LAYER = 5


@dataclass(frozen=True)
class BBox:
    """Axis-aligned bounding box."""

    x1: float
    y1: float
    x2: float
    y2: float

    def __post_init__(self) -> None:
        # Normalize so x1 <= x2, y1 <= y2
        if self.x1 > self.x2 or self.y1 > self.y2:
            nx1, ny1 = min(self.x1, self.x2), min(self.y1, self.y2)
            nx2, ny2 = max(self.x1, self.x2), max(self.y1, self.y2)
            object.__setattr__(self, "x1", nx1)
            object.__setattr__(self, "y1", ny1)
            object.__setattr__(self, "x2", nx2)
            object.__setattr__(self, "y2", ny2)

    @property
    def width(self) -> float:
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        return self.y2 - self.y1

    @property
    def center(self) -> tuple[float, float]:
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)

    @property
    def area(self) -> float:
        return self.width * self.height

    def overlaps(self, other: BBox) -> bool:
        """Test whether two AABBs overlap (share interior area)."""
        return (
            self.x1 < other.x2
            and self.x2 > other.x1
            and self.y1 < other.y2
            and self.y2 > other.y1
        )

    def contains_point(self, x: float, y: float) -> bool:
        """Test whether a point lies inside or on the boundary."""
        return self.x1 <= x <= self.x2 and self.y1 <= y <= self.y2

    def union(self, other: BBox) -> BBox:
        """Return the smallest BBox enclosing both."""
        return BBox(
            min(self.x1, other.x1),
            min(self.y1, other.y1),
            max(self.x2, other.x2),
            max(self.y2, other.y2),
        )

    def expanded(self, margin: float) -> BBox:
        """Return a new BBox grown by margin on all sides."""
        return BBox(
            self.x1 - margin,
            self.y1 - margin,
            self.x2 + margin,
            self.y2 + margin,
        )

    @classmethod
    def merge(cls, *bboxes: BBox) -> BBox:
        """Merge multiple BBoxes into one enclosing BBox."""
        if not bboxes:
            raise ValueError("Cannot merge zero bounding boxes")
        result = bboxes[0]
        for b in bboxes[1:]:
            result = result.union(b)
        return result



def transform_point(
    px: float,
    py: float,
    cx: float,
    cy: float,
    rotation: int,
    mirror: int,
) -> tuple[float, float]:
    """Transform a point from local to schematic coordinates.

    xschem applies transforms in order: mirror → rotate → translate.

    Args:
        px, py: Point in local coordinates.
        cx, cy: Instance origin in schematic coordinates.
        rotation: 0-3 (0°, 90°, 180°, 270°).
        mirror: 0 or 1 (mirror about Y axis before rotation).

    Returns:
        (x, y) in schematic coordinates.
    """
    if mirror:
        px = -px

    if rotation == 0:
        rx, ry = px, py
    elif rotation == 1:
        rx, ry = -py, px
    elif rotation == 2:
        rx, ry = -px, -py
    elif rotation == 3:
        rx, ry = py, -px
    else:
        rx, ry = px, py

    return cx + rx, cy + ry


def transform_bbox(
    bbox: BBox,
    cx: float,
    cy: float,
    rotation: int,
    mirror: int,
) -> BBox:
    """Transform a local-coordinate BBox to schematic coordinates.

    Transforms all four corners, then returns the AABB of the result.
    """
    corners = [
        (bbox.x1, bbox.y1),
        (bbox.x2, bbox.y1),
        (bbox.x2, bbox.y2),
        (bbox.x1, bbox.y2),
    ]
    transformed = [transform_point(x, y, cx, cy, rotation, mirror) for x, y in corners]
    xs = [p[0] for p in transformed]
    ys = [p[1] for p in transformed]
    return BBox(min(xs), min(ys), max(xs), max(ys))



def bbox_from_elements(elements: Sequence[Element]) -> BBox | None:
    """Compute the AABB enclosing a list of graphic elements.

    Excludes layer-5 (pin) boxes. Returns None if no graphic elements
    contribute coordinates.
    """
    xs: list[float] = []
    ys: list[float] = []

    for e in elements:
        if isinstance(e, GraphicLine):
            xs.extend([e.x1, e.x2])
            ys.extend([e.y1, e.y2])
        elif isinstance(e, Box):
            if e.layer == _PIN_LAYER:
                continue
            xs.extend([e.x1, e.x2])
            ys.extend([e.y1, e.y2])
        elif isinstance(e, Arc):
            # Conservative: use full circle AABB
            xs.extend([e.x - e.r, e.x + e.r])
            ys.extend([e.y - e.r, e.y + e.r])
        elif isinstance(e, Polygon):
            for px, py in e.points:
                xs.append(px)
                ys.append(py)

    if not xs:
        return None

    return BBox(min(xs), min(ys), max(xs), max(ys))



def point_on_segment(
    px: float,
    py: float,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    tol: float = 1e-9,
) -> bool:
    """Test whether point (px, py) lies on segment (x1,y1)-(x2,y2)."""
    # Cross product to check collinearity
    cross = (px - x1) * (y2 - y1) - (py - y1) * (x2 - x1)
    if abs(cross) > tol:
        return False

    # Check within bounding box of segment
    min_x, max_x = (x1, x2) if x1 <= x2 else (x2, x1)
    min_y, max_y = (y1, y2) if y1 <= y2 else (y2, y1)
    return (min_x - tol) <= px <= (max_x + tol) and (min_y - tol) <= py <= (max_y + tol)


def segment_crosses_bbox(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    bbox: BBox,
) -> bool:
    """Test whether a line segment intersects a BBox interior.

    Returns True if any part of the segment passes through the box.
    Uses Cohen-Sutherland outcode approach for efficiency.
    """
    # Outcodes
    INSIDE, LEFT, RIGHT, BOTTOM, TOP = 0, 1, 2, 4, 8

    def _outcode(x: float, y: float) -> int:
        code = INSIDE
        if x < bbox.x1:
            code |= LEFT
        elif x > bbox.x2:
            code |= RIGHT
        if y < bbox.y1:
            code |= BOTTOM
        elif y > bbox.y2:
            code |= TOP
        return code

    code1 = _outcode(x1, y1)
    code2 = _outcode(x2, y2)

    # Iterative clipping
    for _ in range(20):  # bounded iterations
        if not (code1 | code2):
            # Both inside
            return True
        if code1 & code2:
            # Both in same outside region
            return False

        # Pick the point outside the box
        code_out = code1 if code1 else code2

        if code_out & TOP:
            x = x1 + (x2 - x1) * (bbox.y2 - y1) / (y2 - y1) if y2 != y1 else x1
            y = bbox.y2
        elif code_out & BOTTOM:
            x = x1 + (x2 - x1) * (bbox.y1 - y1) / (y2 - y1) if y2 != y1 else x1
            y = bbox.y1
        elif code_out & RIGHT:
            y = y1 + (y2 - y1) * (bbox.x2 - x1) / (x2 - x1) if x2 != x1 else y1
            x = bbox.x2
        elif code_out & LEFT:
            y = y1 + (y2 - y1) * (bbox.x1 - x1) / (x2 - x1) if x2 != x1 else y1
            x = bbox.x1
        else:
            break

        if code_out == code1:
            x1, y1 = x, y
            code1 = _outcode(x1, y1)
        else:
            x2, y2 = x, y
            code2 = _outcode(x2, y2)

    return False


def segments_intersect(
    ax1: float,
    ay1: float,
    ax2: float,
    ay2: float,
    bx1: float,
    by1: float,
    bx2: float,
    by2: float,
    tol: float = 1e-9,
) -> tuple[float, float] | None:
    """Find the intersection point of two line segments, if any.

    Returns the (x, y) intersection point, or None if the segments
    don't cross. Collinear overlapping segments return None (no single
    intersection point).
    """
    dx_a = ax2 - ax1
    dy_a = ay2 - ay1
    dx_b = bx2 - bx1
    dy_b = by2 - by1

    denom = dx_a * dy_b - dy_a * dx_b
    if abs(denom) < tol:
        # Parallel or collinear
        return None

    t = ((bx1 - ax1) * dy_b - (by1 - ay1) * dx_b) / denom
    u = ((bx1 - ax1) * dy_a - (by1 - ay1) * dx_a) / denom

    if -tol <= t <= 1 + tol and -tol <= u <= 1 + tol:
        ix = ax1 + t * dx_a
        iy = ay1 + t * dy_a
        return (ix, iy)

    return None



class GeometryQuery:
    """Spatial query interface for a schematic and its symbols.

    Computes and caches bounding boxes, pin positions, and overlap
    information.  Operates on an immutable snapshot — create a new
    instance after mutations.

    Usage::

        gq = GeometryQuery(schematic, libs)
        bb = gq.component_bbox("U1")
        overlaps = gq.overlapping_components()
    """

    def __init__(self, schematic: Schematic, libs: SymbolLibrary) -> None:
        self._sch = schematic
        self._libs = libs
        # Lazy caches
        self._comp_bboxes: dict[str, BBox] | None = None
        self._pin_positions: list[tuple[float, float, str, str]] | None = None

    def symbol_bbox(self, symbol: Symbol) -> BBox | None:
        """Bounding box of a symbol in local coordinates."""
        return bbox_from_elements(symbol.elements)

    def component_bbox(self, name: str) -> BBox | None:
        """Placed bounding box of a named component."""
        bboxes = self._get_comp_bboxes()
        if name not in bboxes:
            comp = self._sch.get_component(name)
            if comp is None:
                raise ValueError(f"Component '{name}' not found")
            # Component exists but has no resolvable bbox
            return None
        return bboxes[name]

    def component_bboxes(self) -> dict[str, BBox]:
        """All named components with their placed bounding boxes."""
        return dict(self._get_comp_bboxes())

    def schematic_bbox(self) -> BBox | None:
        """Bounding box of the entire schematic."""
        bboxes: list[BBox] = []

        # Graphic elements
        graphic_bbox = bbox_from_elements(self._sch.elements)
        if graphic_bbox is not None:
            bboxes.append(graphic_bbox)

        # Net endpoints
        for n in self._sch.nets:
            bboxes.append(BBox(
                min(n.x1, n.x2), min(n.y1, n.y2),
                max(n.x1, n.x2), max(n.y1, n.y2),
            ))

        # Text positions
        for t in self._sch.texts:
            bboxes.append(BBox(t.x, t.y, t.x, t.y))

        # Component bboxes (includes position even without symbol)
        for c in self._sch.components:
            bboxes.append(BBox(c.x, c.y, c.x, c.y))
        for bb in self._get_comp_bboxes().values():
            bboxes.append(bb)

        if not bboxes:
            return None
        return BBox.merge(*bboxes)

    def pin_positions(self) -> list[tuple[float, float, str, str]]:
        """All component pin positions as (x, y, comp_name, pin_name)."""
        if self._pin_positions is not None:
            return self._pin_positions

        result: list[tuple[float, float, str, str]] = []
        for comp in self._sch.components:
            sym = self._libs.resolve(comp.symbol)
            if sym is None:
                continue
            comp_label = comp.label
            for pin in sym.pins:
                px, py = transform_point(
                    pin.x, pin.y, comp.x, comp.y, comp.rotation, comp.mirror
                )
                result.append((px, py, comp_label, pin.name))

        self._pin_positions = result
        return result

    def overlapping_components(self) -> list[tuple[str, str]]:
        """Find pairs of named components with overlapping bboxes."""
        items = list(self._get_comp_bboxes().items())
        result: list[tuple[str, str]] = []
        for i, (name_a, bbox_a) in enumerate(items):
            for j in range(i + 1, len(items)):
                name_b, bbox_b = items[j]
                if bbox_a.overlaps(bbox_b):
                    result.append((name_a, name_b))
        return result

    # -- internal --

    def _get_comp_bboxes(self) -> dict[str, BBox]:
        if self._comp_bboxes is not None:
            return self._comp_bboxes

        result: dict[str, BBox] = {}
        for comp in self._sch.components:
            if not comp.name:
                continue
            sym = self._libs.resolve(comp.symbol)
            if sym is None:
                continue
            local_bbox = bbox_from_elements(sym.elements)
            if local_bbox is None:
                continue
            result[comp.name] = transform_bbox(
                local_bbox, comp.x, comp.y, comp.rotation, comp.mirror
            )
        self._comp_bboxes = result
        return result
