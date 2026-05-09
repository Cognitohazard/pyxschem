"""Tests for pyxschem.geometry."""

from __future__ import annotations

import pytest

from pyxschem.geometry import (
    BBox,
    bbox_from_elements,
    pin_side,
    point_on_segment,
    segment_crosses_bbox,
    segments_intersect,
    transform_bbox,
    transform_point,
)
from pyxschem.model import Arc, Box, GraphicLine, Polygon

# ---------------------------------------------------------------------------
# BBox
# ---------------------------------------------------------------------------


class TestBBox:
    def test_basic_properties(self):
        b = BBox(0, 0, 10, 20)
        assert b.width == 10
        assert b.height == 20
        assert b.center == (5, 10)
        assert b.area == 200

    def test_normalization(self):
        b = BBox(10, 20, 0, 0)
        assert b.x1 == 0
        assert b.y1 == 0
        assert b.x2 == 10
        assert b.y2 == 20

    def test_overlaps_true(self):
        a = BBox(0, 0, 10, 10)
        b = BBox(5, 5, 15, 15)
        assert a.overlaps(b)
        assert b.overlaps(a)

    def test_overlaps_false_no_contact(self):
        a = BBox(0, 0, 10, 10)
        b = BBox(20, 20, 30, 30)
        assert not a.overlaps(b)

    def test_overlaps_false_edge_touching(self):
        a = BBox(0, 0, 10, 10)
        b = BBox(10, 0, 20, 10)
        assert not a.overlaps(b)

    def test_contains_point_inside(self):
        b = BBox(0, 0, 10, 10)
        assert b.contains_point(5, 5)

    def test_contains_point_on_boundary(self):
        b = BBox(0, 0, 10, 10)
        assert b.contains_point(0, 0)
        assert b.contains_point(10, 10)

    def test_contains_point_outside(self):
        b = BBox(0, 0, 10, 10)
        assert not b.contains_point(15, 5)

    def test_union(self):
        a = BBox(0, 0, 10, 10)
        b = BBox(5, 5, 20, 20)
        u = a.union(b)
        assert u == BBox(0, 0, 20, 20)

    def test_expanded(self):
        b = BBox(10, 10, 20, 20)
        e = b.expanded(5)
        assert e == BBox(5, 5, 25, 25)

    def test_merge(self):
        result = BBox.merge(BBox(0, 0, 5, 5), BBox(10, 10, 15, 15), BBox(-5, 0, 0, 3))
        assert result == BBox(-5, 0, 15, 15)

    def test_merge_single(self):
        b = BBox(1, 2, 3, 4)
        assert BBox.merge(b) == b

    def test_merge_empty_raises(self):
        with pytest.raises(ValueError):
            BBox.merge()

    def test_frozen(self):
        b = BBox(0, 0, 10, 10)
        with pytest.raises(AttributeError):
            b.x1 = 5  # type: ignore[misc]


# ---------------------------------------------------------------------------
# transform_point
# ---------------------------------------------------------------------------


class TestTransformPoint:
    def test_identity(self):
        assert transform_point(10, 20, 100, 200, 0, 0) == (110, 220)

    def test_rotation_90(self):
        assert transform_point(10, 0, 0, 0, 1, 0) == (0, 10)

    def test_rotation_180(self):
        assert transform_point(10, 20, 0, 0, 2, 0) == (-10, -20)

    def test_rotation_270(self):
        assert transform_point(10, 0, 0, 0, 3, 0) == (0, -10)

    def test_mirror_only(self):
        assert transform_point(10, 20, 0, 0, 0, 1) == (-10, 20)

    def test_mirror_then_rotate_90(self):
        # Mirror: (10, 20) -> (-10, 20)
        # Rotate 90: (-10, 20) -> (-20, -10)
        assert transform_point(10, 20, 0, 0, 1, 1) == (-20, -10)

    def test_with_translation(self):
        assert transform_point(10, 20, 50, 60, 0, 0) == (60, 80)

    def test_full_transform(self):
        # Mirror: (5, 0) -> (-5, 0), Rotate 90: (-5,0) -> (0,-5), Translate: (100, 200)
        assert transform_point(5, 0, 100, 200, 1, 1) == (100, 195)


# ---------------------------------------------------------------------------
# transform_bbox
# ---------------------------------------------------------------------------


class TestTransformBBox:
    def test_identity(self):
        b = BBox(0, 0, 10, 20)
        result = transform_bbox(b, 100, 200, 0, 0)
        assert result == BBox(100, 200, 110, 220)

    def test_rotation_90(self):
        b = BBox(0, 0, 10, 20)
        result = transform_bbox(b, 0, 0, 1, 0)
        assert result == BBox(-20, 0, 0, 10)

    def test_rotation_180(self):
        b = BBox(0, 0, 10, 20)
        result = transform_bbox(b, 0, 0, 2, 0)
        assert result == BBox(-10, -20, 0, 0)

    def test_mirror_and_rotate(self):
        b = BBox(0, 0, 10, 20)
        result = transform_bbox(b, 50, 50, 1, 1)
        # mirror → rot90 → translate(50,50): corners land at (30..50, 40..50)
        assert result == BBox(30, 40, 50, 50)


# ---------------------------------------------------------------------------
# bbox_from_elements
# ---------------------------------------------------------------------------


class TestBBoxFromElements:
    def test_empty(self):
        assert bbox_from_elements([]) is None

    def test_lines(self):
        elements = [
            GraphicLine(layer=4, x1=0, y1=0, x2=10, y2=20),
            GraphicLine(layer=4, x1=-5, y1=10, x2=5, y2=30),
        ]
        result = bbox_from_elements(elements)
        assert result == BBox(-5, 0, 10, 30)

    def test_boxes(self):
        elements = [Box(layer=4, x1=0, y1=0, x2=20, y2=10)]
        result = bbox_from_elements(elements)
        assert result == BBox(0, 0, 20, 10)

    def test_excludes_pin_layer(self):
        elements = [
            Box(layer=5, x1=-100, y1=-100, x2=100, y2=100),
            GraphicLine(layer=4, x1=0, y1=0, x2=10, y2=10),
        ]
        result = bbox_from_elements(elements)
        assert result == BBox(0, 0, 10, 10)

    def test_only_pin_layer_returns_none(self):
        elements = [Box(layer=5, x1=0, y1=0, x2=10, y2=10)]
        assert bbox_from_elements(elements) is None

    def test_arcs(self):
        elements = [Arc(layer=4, x=50, y=50, r=10, start_angle=0, sweep_angle=90)]
        result = bbox_from_elements(elements)
        assert result == BBox(40, 40, 60, 60)

    def test_polygons(self):
        elements = [Polygon(layer=4, points=[(0, 0), (10, 5), (5, 15)])]
        result = bbox_from_elements(elements)
        assert result == BBox(0, 0, 10, 15)

    def test_mixed_elements(self):
        elements = [
            GraphicLine(layer=4, x1=0, y1=0, x2=10, y2=10),
            Box(layer=4, x1=5, y1=5, x2=25, y2=15),
            Arc(layer=4, x=20, y=20, r=5, start_angle=0, sweep_angle=360),
        ]
        result = bbox_from_elements(elements)
        assert result == BBox(0, 0, 25, 25)


# ---------------------------------------------------------------------------
# point_on_segment
# ---------------------------------------------------------------------------


class TestPointOnSegment:
    def test_midpoint(self):
        assert point_on_segment(5, 5, 0, 0, 10, 10)

    def test_endpoint(self):
        assert point_on_segment(0, 0, 0, 0, 10, 10)
        assert point_on_segment(10, 10, 0, 0, 10, 10)

    def test_horizontal_segment(self):
        assert point_on_segment(5, 0, 0, 0, 10, 0)
        assert not point_on_segment(5, 1, 0, 0, 10, 0)

    def test_vertical_segment(self):
        assert point_on_segment(0, 5, 0, 0, 0, 10)
        assert not point_on_segment(1, 5, 0, 0, 0, 10)

    def test_off_segment_but_collinear(self):
        assert not point_on_segment(15, 15, 0, 0, 10, 10)

    def test_not_collinear(self):
        assert not point_on_segment(3, 5, 0, 0, 10, 10)


# ---------------------------------------------------------------------------
# segment_crosses_bbox
# ---------------------------------------------------------------------------


class TestSegmentCrossesBBox:
    def test_segment_inside(self):
        b = BBox(0, 0, 20, 20)
        assert segment_crosses_bbox(5, 5, 15, 15, b)

    def test_segment_through(self):
        b = BBox(5, 5, 15, 15)
        assert segment_crosses_bbox(0, 10, 20, 10, b)

    def test_segment_outside(self):
        b = BBox(0, 0, 10, 10)
        assert not segment_crosses_bbox(20, 20, 30, 30, b)

    def test_segment_parallel_outside(self):
        b = BBox(0, 0, 10, 10)
        assert not segment_crosses_bbox(0, 15, 10, 15, b)

    def test_segment_touching_edge(self):
        b = BBox(0, 0, 10, 10)
        # Horizontal segment along top edge — one endpoint at corner
        assert segment_crosses_bbox(0, 0, 5, 5, b)

    def test_diagonal_through(self):
        b = BBox(5, 5, 15, 15)
        assert segment_crosses_bbox(0, 0, 20, 20, b)


# ---------------------------------------------------------------------------
# segments_intersect
# ---------------------------------------------------------------------------


class TestSegmentsIntersect:
    def test_crossing(self):
        result = segments_intersect(0, 0, 10, 10, 0, 10, 10, 0)
        assert result is not None
        assert abs(result[0] - 5) < 1e-6
        assert abs(result[1] - 5) < 1e-6

    def test_t_junction(self):
        result = segments_intersect(0, 5, 10, 5, 5, 0, 5, 10)
        assert result is not None
        assert abs(result[0] - 5) < 1e-6
        assert abs(result[1] - 5) < 1e-6

    def test_no_intersection(self):
        assert segments_intersect(0, 0, 5, 0, 0, 5, 5, 5) is None

    def test_parallel(self):
        assert segments_intersect(0, 0, 10, 0, 0, 1, 10, 1) is None

    def test_collinear_overlapping(self):
        # Collinear overlapping segments return None (no single point)
        assert segments_intersect(0, 0, 10, 0, 5, 0, 15, 0) is None

    def test_endpoint_touching(self):
        result = segments_intersect(0, 0, 5, 0, 5, 0, 10, 0)
        # Collinear, returns None
        assert result is None

    def test_l_shaped(self):
        result = segments_intersect(0, 0, 10, 0, 10, 0, 10, 10)
        assert result is not None
        assert abs(result[0] - 10) < 1e-6
        assert abs(result[1] - 0) < 1e-6

    def test_miss(self):
        assert segments_intersect(0, 0, 3, 0, 5, 1, 5, 10) is None


# ---------------------------------------------------------------------------
# pin_side — outward lead direction under rotation/mirror
# ---------------------------------------------------------------------------


class TestPinSide:
    """A bbox of (-10,-30,10,30) with pins on each edge — the
    classification must follow rotation/mirror consistently with
    transform_point."""

    BBOX = BBox(-10, -30, 10, 30)

    def test_local_sides(self):
        # In local coords: y grows downward, so the pin at (0, -30) is
        # at the top of the body (xschem screen "up").
        assert pin_side(0, -30, self.BBOX) == "up"
        assert pin_side(0, 30, self.BBOX) == "down"
        assert pin_side(10, 0, self.BBOX) == "right"
        assert pin_side(-10, 0, self.BBOX) == "left"

    def test_rotation_90(self):
        # rot=1 (xschem 90° rotation) sends (px,py) → (-py, px).
        # Mapping: up→right, down→left, right→down, left→up.
        assert pin_side(0, -30, self.BBOX, rotation=1) == "right"
        assert pin_side(0, 30, self.BBOX, rotation=1) == "left"
        assert pin_side(10, 0, self.BBOX, rotation=1) == "down"
        assert pin_side(-10, 0, self.BBOX, rotation=1) == "up"

    def test_rotation_180(self):
        assert pin_side(0, -30, self.BBOX, rotation=2) == "down"
        assert pin_side(10, 0, self.BBOX, rotation=2) == "left"

    def test_mirror(self):
        # Mirror flips x; left and right swap, top/bottom stay.
        assert pin_side(10, 0, self.BBOX, mirror=1) == "left"
        assert pin_side(-10, 0, self.BBOX, mirror=1) == "right"
        assert pin_side(0, -30, self.BBOX, mirror=1) == "up"

    def test_diagonal_pin_picks_dominant_axis(self):
        # Pin nearer the right edge than the top, even though both are
        # off-center, must classify as "right".
        assert pin_side(10, -10, self.BBOX) == "right"
        # And vice versa.
        assert pin_side(2, -30, self.BBOX) == "up"
