"""Tests for schematic validation."""

from unittest.mock import MagicMock, PropertyMock

from conftest import make_symbol, mock_libs

from pyxschem.schematic import Schematic
from pyxschem.symbol import Pin
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
            -10, -10, 10, 10,
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
            -10, -10, 10, 10,
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
