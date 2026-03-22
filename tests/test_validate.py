"""Tests for schematic validation."""

from unittest.mock import MagicMock, PropertyMock

from pyxschem.schematic import Schematic
from pyxschem.symbol import Pin
from pyxschem.validate import validate


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
