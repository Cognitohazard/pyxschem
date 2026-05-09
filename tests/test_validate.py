"""Tests for schematic validation."""

from unittest.mock import MagicMock, PropertyMock

from conftest import make_symbol, mock_libs

from pyxschem.schematic import Schematic
from pyxschem.symbol import Pin, Symbol
from pyxschem.validate import Validator, validate


class TestDuplicateNames:
    def test_no_duplicates(self):
        sch = Schematic.new()
        sch.add_component("r.sym", 0, 0, attributes={"name": "R1"})
        sch.add_component("r.sym", 100, 0, attributes={"name": "R2"})
        result = validate(sch)
        assert result.is_valid
        assert not any(i.category == "duplicate_name" for i in result.issues)

    def test_duplicate_names_reported_as_error(self):
        sch = Schematic.new()
        sch.add_component("r.sym", 0, 0, attributes={"name": "R1"})
        sch.add_component("r.sym", 100, 0, attributes={"name": "R1"})
        result = validate(sch)
        assert not result.is_valid
        dup_issues = [i for i in result.issues if i.category == "duplicate_name"]
        assert len(dup_issues) == 2  # one per duplicated component
        assert all(i.severity == "error" for i in dup_issues)


class TestMissingNames:
    def test_no_warning_when_all_named(self):
        sch = Schematic.new()
        sch.add_component("r.sym", 0, 0, attributes={"name": "R1"})
        result = validate(sch)
        assert not any(i.category == "missing_name" for i in result.issues)

    def test_missing_name_warning(self):
        sch = Schematic.new()
        sch.add_component("gnd.sym", 0, 0)
        result = validate(sch)
        missing = [i for i in result.issues if i.category == "missing_name"]
        assert len(missing) == 1
        assert missing[0].severity == "warning"
        # warnings don't prevent is_valid
        assert result.is_valid


class TestFloatingNets:
    def test_connected_net_no_warning(self):
        sch = Schematic.new()
        sch.add_component("r.sym", 0, 0, attributes={"name": "R1"})
        sch.add_component("r.sym", 100, 0, attributes={"name": "R2"})
        sch.add_net(0, 0, 100, 0)
        result = validate(sch)
        assert not any(i.category == "floating_net" for i in result.issues)

    def test_floating_net_warning(self):
        sch = Schematic.new()
        # Net with no component or other net at either endpoint
        sch.add_net(500, 500, 600, 500)
        result = validate(sch)
        floating = [i for i in result.issues if i.category == "floating_net"]
        assert len(floating) >= 1
        assert all(i.severity == "warning" for i in floating)

    def test_net_touching_another_net_not_floating(self):
        sch = Schematic.new()
        sch.add_net(0, 0, 100, 0)
        sch.add_net(100, 0, 200, 0)
        result = validate(sch)
        floating = [i for i in result.issues if i.category == "floating_net"]
        # endpoints at (0,0) and (200,0) are floating, but (100,0) is shared
        # The nets at the unshared endpoints should still be flagged
        for issue in floating:
            assert "100" not in issue.message or "0" not in issue.message


class TestUnconnectedPins:
    def _make_libs(self, pins: list[Pin]) -> MagicMock:
        libs = MagicMock()
        sym = MagicMock()
        type(sym).pins = PropertyMock(return_value=pins)
        libs.resolve.return_value = sym
        return libs

    def test_all_pins_connected(self):
        sch = Schematic.new()
        sch.add_component("r.sym", 100, 200, attributes={"name": "R1"})
        # Pin at local (0, 0) → schematic (100, 200)
        # Pin at local (0, 50) → schematic (100, 250)
        sch.add_net(100, 200, 100, 250)
        libs = self._make_libs(
            [
                Pin(name="P", direction="inout", x=0, y=0),
                Pin(name="N", direction="inout", x=0, y=50),
            ]
        )
        result = validate(sch, libs=libs)
        assert not any(i.category == "unconnected_pin" for i in result.issues)

    def test_unconnected_pin_warning(self):
        sch = Schematic.new()
        sch.add_component("r.sym", 100, 200, attributes={"name": "R1"})
        # Only connect one pin
        sch.add_net(100, 200, 100, 200)
        libs = self._make_libs(
            [
                Pin(name="P", direction="inout", x=0, y=0),
                Pin(name="N", direction="inout", x=0, y=50),
            ]
        )
        result = validate(sch, libs=libs)
        unconnected = [i for i in result.issues if i.category == "unconnected_pin"]
        assert len(unconnected) == 1
        assert "N" in unconnected[0].message
        assert unconnected[0].severity == "warning"

    def test_skipped_without_libs(self):
        sch = Schematic.new()
        sch.add_component("r.sym", 100, 200, attributes={"name": "R1"})
        result = validate(sch, libs=None)
        assert not any(i.category == "unconnected_pin" for i in result.issues)

    def test_unresolvable_symbol_skipped(self):
        sch = Schematic.new()
        sch.add_component("unknown.sym", 0, 0, attributes={"name": "X1"})
        libs = MagicMock()
        libs.resolve.return_value = None
        result = validate(sch, libs=libs)
        assert not any(i.category == "unconnected_pin" for i in result.issues)


class TestValidateConvenience:
    def test_schematic_validate_method(self):
        sch = Schematic.new()
        sch.add_component("r.sym", 0, 0, attributes={"name": "R1"})
        result = sch.validate()
        assert result.is_valid


class TestIsValid:
    def test_valid_with_only_warnings(self):
        sch = Schematic.new()
        sch.add_component("r.sym", 0, 0)  # missing name → warning
        result = validate(sch)
        assert result.is_valid

    def test_invalid_with_errors(self):
        sch = Schematic.new()
        sch.add_component("r.sym", 0, 0, attributes={"name": "R1"})
        sch.add_component("r.sym", 100, 0, attributes={"name": "R1"})
        result = validate(sch)
        assert not result.is_valid


class TestCheckNet:
    def test_normal_net_no_warnings(self):
        sch = Schematic.new()
        v = Validator(sch)
        warnings = v.check_net(0, 0, 100, 0)
        assert warnings == []

    def test_diagonal_wire_warning(self):
        sch = Schematic.new()
        v = Validator(sch)
        warnings = v.check_net(0, 0, 100, 50)
        assert len(warnings) == 1
        assert warnings[0].category == "diagonal_wire"

    def test_zero_length_unlabeled_warning(self):
        sch = Schematic.new()
        v = Validator(sch)
        warnings = v.check_net(50, 50, 50, 50)
        assert len(warnings) == 1
        assert warnings[0].category == "zero_length_net"

    def test_zero_length_with_label_ok(self):
        sch = Schematic.new()
        v = Validator(sch)
        warnings = v.check_net(50, 50, 50, 50, label="VDD")
        assert warnings == []


class TestWireCrossesBody:
    def test_wire_through_component(self):
        sym = make_symbol(-10, -10, 10, 10)
        libs = mock_libs(("test.sym", sym))
        sch = Schematic.new()
        sch.add_component("test.sym", x=50, y=0, attributes={"name": "U1"})
        # Wire passes through U1's bbox (40,-10 to 60,10) horizontally
        sch.add_net(0, 0, 100, 0)
        result = validate(sch, libs=libs)
        crosses = [i for i in result.issues if i.category == "wire_crosses_body"]
        assert len(crosses) == 1
        assert "U1" in crosses[0].message

    def test_wire_endpoint_at_component_skipped(self):
        sym = make_symbol(-10, -10, 10, 10)
        libs = mock_libs(("test.sym", sym))
        sch = Schematic.new()
        sch.add_component("test.sym", x=0, y=0, attributes={"name": "U1"})
        # Wire endpoint is inside the component bbox — source/target
        sch.add_net(0, 0, 100, 0)
        result = validate(sch, libs=libs)
        crosses = [i for i in result.issues if i.category == "wire_crosses_body"]
        assert len(crosses) == 0

    def test_wire_outside_component_no_warning(self):
        sym = make_symbol(-5, -5, 5, 5)
        libs = mock_libs(("test.sym", sym))
        sch = Schematic.new()
        sch.add_component("test.sym", x=50, y=50, attributes={"name": "U1"})
        sch.add_net(0, 0, 100, 0)  # far from component
        result = validate(sch, libs=libs)
        crosses = [i for i in result.issues if i.category == "wire_crosses_body"]
        assert len(crosses) == 0


class TestUnintendedJunction:
    def test_crossing_wires(self):
        sch = Schematic.new()
        sch.add_net(0, 5, 10, 5)  # horizontal
        sch.add_net(5, 0, 5, 10)  # vertical — crosses at (5, 5)
        result = validate(sch)
        junctions = [i for i in result.issues if i.category == "unintended_junction"]
        assert len(junctions) == 1

    def test_shared_endpoint_ok(self):
        sch = Schematic.new()
        sch.add_net(0, 0, 10, 0)
        sch.add_net(10, 0, 10, 10)  # shares endpoint (10, 0)
        result = validate(sch)
        junctions = [i for i in result.issues if i.category == "unintended_junction"]
        assert len(junctions) == 0

    def test_non_intersecting_no_warning(self):
        sch = Schematic.new()
        sch.add_net(0, 0, 10, 0)
        sch.add_net(0, 10, 10, 10)  # parallel, no crossing
        result = validate(sch)
        junctions = [i for i in result.issues if i.category == "unintended_junction"]
        assert len(junctions) == 0


class TestPinCollision:
    def test_wire_through_pin(self):
        sym = make_symbol(
            -10,
            -10,
            10,
            10,
            pins=[Pin(name="A", direction="in", x=0, y=0)],
        )
        libs = mock_libs(("test.sym", sym))
        sch = Schematic.new()
        # Component at (50, 0) — pin A at (50, 0)
        sch.add_component("test.sym", x=50, y=0, attributes={"name": "U1"})
        # Wire passes through pin A but doesn't have endpoint there
        sch.add_net(0, 0, 100, 0)
        result = validate(sch, libs=libs)
        collisions = [i for i in result.issues if i.category == "pin_collision"]
        assert len(collisions) == 1
        assert "A" in collisions[0].message

    def test_wire_endpoint_at_pin_ok(self):
        sym = make_symbol(
            -10,
            -10,
            10,
            10,
            pins=[Pin(name="A", direction="in", x=0, y=0)],
        )
        libs = mock_libs(("test.sym", sym))
        sch = Schematic.new()
        sch.add_component("test.sym", x=50, y=0, attributes={"name": "U1"})
        # Wire endpoint is at pin A — intentional
        sch.add_net(50, 0, 100, 0)
        result = validate(sch, libs=libs)
        collisions = [i for i in result.issues if i.category == "pin_collision"]
        assert len(collisions) == 0


class TestComponentOverlap:
    def test_overlapping_components(self):
        sym = make_symbol(-10, -10, 10, 10)
        libs = mock_libs(("test.sym", sym))
        sch = Schematic.new()
        sch.add_component("test.sym", x=0, y=0, attributes={"name": "U1"})
        sch.add_component("test.sym", x=5, y=0, attributes={"name": "U2"})  # overlaps
        result = validate(sch, libs=libs)
        overlaps = [i for i in result.issues if i.category == "component_overlap"]
        assert len(overlaps) == 1
        assert "U1" in overlaps[0].message
        assert "U2" in overlaps[0].message

    def test_non_overlapping_components(self):
        sym = make_symbol(-5, -5, 5, 5)
        libs = mock_libs(("test.sym", sym))
        sch = Schematic.new()
        sch.add_component("test.sym", x=0, y=0, attributes={"name": "U1"})
        sch.add_component("test.sym", x=100, y=0, attributes={"name": "U2"})
        result = validate(sch, libs=libs)
        overlaps = [i for i in result.issues if i.category == "component_overlap"]
        assert len(overlaps) == 0


# ---------------------------------------------------------------------------
# Label/port symbol tolerance & rotation-aware checks (added with codex fixes)
# ---------------------------------------------------------------------------


def _label_symbol() -> Symbol:
    """A minimal label-type symbol for validator idiom tests."""
    return Symbol.from_text(
        "v {xschem version=3.4.5 file_version=1.2}\n"
        "G {}\n"
        "K {type=label net_name=true format=\"*.alias @lab\" "
        "template=\"name=p1 lab=xxx\"}\n"
        "V {}\nS {}\nE {}\n"
        "B 5 -2.5 -2.5 2.5 2.5 {name=p dir=in}\n"
    )


class TestLabelSymbolTolerance:
    def test_label_on_wire_does_not_trigger_wire_crosses_body(self):
        # A wire passes through where a lab_pin sits — the label-on-wire
        # idiom must be allowed.
        res = make_symbol(-10, -10, 10, 10)
        res.add_pin("P", "in", 0, -10)
        res.add_pin("M", "in", 0, 10)
        libs = mock_libs(("res.sym", res), ("lab_pin.sym", _label_symbol()))
        sch = Schematic.new()
        sch.add_component("res.sym", 0, 0, attributes={"name": "R1"})
        sch.add_net(0, -10, 100, -10)               # rail at the P pin
        sch.add_component("lab_pin.sym", 50, -10,
                           attributes={"name": "lp_1", "lab": "VDD"})
        result = validate(sch, libs=libs)
        wire_through = [i for i in result.issues
                          if i.category == "wire_crosses_body"]
        pin_through = [i for i in result.issues
                         if i.category == "pin_collision"]
        assert wire_through == []
        assert pin_through == []

    def test_non_label_components_still_flagged(self):
        # A regular component sitting on a wire should still trigger the
        # warning — the tolerance is scoped to label-type symbols.
        res = make_symbol(-10, -10, 10, 10)
        res.add_pin("P", "in", 0, -10)
        libs = mock_libs(("res.sym", res))
        sch = Schematic.new()
        sch.add_component("res.sym", 50, 0, attributes={"name": "R1"})
        # Wire passes straight through R1's bbox (-10..10 around 50, 0).
        sch.add_net(0, 0, 100, 0)
        result = validate(sch, libs=libs)
        cross = [i for i in result.issues
                  if i.category == "wire_crosses_body"]
        assert any("R1" in i.message for i in cross)


class TestCoincidentPinsAreConnected:
    def test_two_pins_at_same_point_dont_trigger_unconnected(self):
        # No wire, but two coincident pins → xschem treats as a short.
        res = make_symbol(-10, -10, 10, 10)
        res.add_pin("P", "in", 0, 0)
        libs = mock_libs(("res.sym", res), ("lab_pin.sym", _label_symbol()))
        sch = Schematic.new()
        sch.add_component("res.sym", 50, 50, attributes={"name": "R1"})
        sch.add_component("lab_pin.sym", 50, 50,
                           attributes={"name": "lp_1", "lab": "VDD"})
        result = validate(sch, libs=libs)
        unconnected = [i for i in result.issues
                         if i.category == "unconnected_pin"
                         and "'R1'" in i.message]
        assert unconnected == []


class TestFloatingNetRotationAware:
    def test_rotated_pin_endpoint_not_floating(self):
        res = make_symbol(-10, -10, 10, 10)
        res.add_pin("P", "in", 0, -30)
        libs = mock_libs(("res.sym", res))
        sch = Schematic.new()
        # Rotation 1: pin (0,-30) lands at (cx+30, cy+0) = (130, -100)
        sch.add_component("res.sym", 100, -100, rotation=1,
                           attributes={"name": "R1"})
        # Net endpoint at the rotated pin's actual location.
        sch.add_net(130, -100, 200, -100)
        result = validate(sch, libs=libs)
        floating = [i for i in result.issues
                     if i.category == "floating_net"]
        # The (130,-100) endpoint is on R1's rotated pin and must NOT
        # be flagged as floating; the (200,-100) far endpoint legitimately
        # is, and that's fine.
        for i in floating:
            assert "(130, -100)" not in i.message


class TestNetGeometryFoldedIntoValidate:
    """``diagonal_wire`` and ``zero_length_net`` were originally only
    reachable via :meth:`Validator.check_net`. They are now folded into
    the main :func:`validate` pass."""

    def test_validate_reports_diagonal_wire(self):
        sch = Schematic.new()
        sch.add_net(0, 0, 100, 100)  # diagonal
        result = validate(sch)
        cats = {i.category for i in result.issues}
        assert "diagonal_wire" in cats

    def test_validate_reports_zero_length_net(self):
        sch = Schematic.new()
        sch.add_net(50, 50, 50, 50)  # degenerate
        result = validate(sch)
        cats = {i.category for i in result.issues}
        assert "zero_length_net" in cats

    def test_zero_length_net_with_label_is_ok(self):
        """A zero-length labelled net is a deliberate label-only
        marker; not an issue."""
        sch = Schematic.new()
        sch.add_net(50, 50, 50, 50, label="VDD")
        result = validate(sch)
        cats = {i.category for i in result.issues}
        assert "zero_length_net" not in cats

    def test_orthogonal_net_passes(self):
        sch = Schematic.new()
        sch.add_net(0, 0, 100, 0)  # horizontal — fine
        sch.add_net(0, 0, 0, 100)  # vertical — fine
        result = validate(sch)
        cats = {i.category for i in result.issues}
        assert "diagonal_wire" not in cats
        assert "zero_length_net" not in cats
