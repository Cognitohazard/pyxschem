"""Tests for generation helpers — pin transforms and wiring API."""

from pathlib import Path

import pytest

from pyxschem import Schematic, SymbolLibrary
from pyxschem.generate import transform_pin

HIER_FIXTURES = Path(__file__).parent / "fixtures" / "hierarchy"


class TestTransformPin:
    def test_no_transform(self):
        x, y = transform_pin(0, -30, 200, -100, rotation=0, mirror=0)
        assert (x, y) == (200, -130)

    def test_rotation_0(self):
        x, y = transform_pin(10, 20, 100, 100, rotation=0, mirror=0)
        assert (x, y) == (110, 120)

    def test_rotation_1(self):
        # 90°: (px, py) → (-py, px)
        x, y = transform_pin(10, 20, 100, 100, rotation=1, mirror=0)
        assert (x, y) == (100 + (-20), 100 + 10)
        assert (x, y) == (80, 110)

    def test_rotation_2(self):
        # 180°: (px, py) → (-px, -py)
        x, y = transform_pin(10, 20, 100, 100, rotation=2, mirror=0)
        assert (x, y) == (90, 80)

    def test_rotation_3(self):
        # 270°: (px, py) → (py, -px)
        x, y = transform_pin(10, 20, 100, 100, rotation=3, mirror=0)
        assert (x, y) == (120, 90)

    def test_mirror_only(self):
        # Mirror: negate px, then no rotation
        x, y = transform_pin(10, 20, 100, 100, rotation=0, mirror=1)
        assert (x, y) == (90, 120)  # -10 + 100, 20 + 100

    def test_mirror_with_rotation_1(self):
        # Mirror first: (10, 20) → (-10, 20)
        # Then rotate 90°: (-10, 20) → (-20, -10)
        # Then translate: (100-20, 100-10) = (80, 90)
        x, y = transform_pin(10, 20, 100, 100, rotation=1, mirror=1)
        assert (x, y) == (80, 90)

    def test_mirror_with_rotation_2(self):
        # Mirror: (10, 20) → (-10, 20)
        # Rotate 180°: (-10, 20) → (10, -20)
        # Translate: (110, 80)
        x, y = transform_pin(10, 20, 100, 100, rotation=2, mirror=1)
        assert (x, y) == (110, 80)

    def test_origin_pin(self):
        x, y = transform_pin(0, 0, 300, -200, rotation=2, mirror=1)
        assert (x, y) == (300, -200)

    def test_float_coordinates(self):
        x, y = transform_pin(2.5, -7.5, 100.5, 200.5, rotation=0, mirror=0)
        assert (x, y) == (103.0, 193.0)


class TestAddNet:
    def test_add_net_with_label(self):
        sch = Schematic.new()
        net = sch.add_net(100, -200, 100, -100, label="VDD")
        assert net.label == "VDD"
        assert net.x1 == 100
        assert net.y1 == -200
        assert net.x2 == 100
        assert net.y2 == -100
        assert len(sch.nets) == 1

    def test_add_net_no_label(self):
        sch = Schematic.new()
        net = sch.add_net(0, 0, 100, 0)
        assert net.label is None
        assert net.attributes == {}

    def test_add_multiple_nets(self):
        sch = Schematic.new()
        sch.add_net(0, 0, 100, 0, label="A")
        sch.add_net(0, 0, 0, 100, label="B")
        assert len(sch.nets) == 2


class TestPinPosition:
    def test_pin_position_no_rotation(self):
        libs = SymbolLibrary([HIER_FIXTURES])
        sch = Schematic.from_text(
            "v {xschem version=3.4.5 file_version=1.2}\n"
            "G {}\nK {}\nV {}\nS {}\nE {}\n"
            "C {resistor.sym} 200 -100 0 0 {name=R1 value=10k}\n"
        )
        px, py = sch.pin_position("R1", "P", libs)
        # resistor.sym pin P is at box center: (0, -30)
        # Component at (200, -100), rot=0, mir=0
        assert px == 200.0
        assert py == -130.0

    def test_pin_position_second_pin(self):
        libs = SymbolLibrary([HIER_FIXTURES])
        sch = Schematic.from_text(
            "v {xschem version=3.4.5 file_version=1.2}\n"
            "G {}\nK {}\nV {}\nS {}\nE {}\n"
            "C {resistor.sym} 200 -100 0 0 {name=R1 value=10k}\n"
        )
        px, py = sch.pin_position("R1", "M", libs)
        # resistor.sym pin M is at box center: (0, 30)
        assert px == 200.0
        assert py == -70.0

    def test_pin_position_missing_component(self):
        libs = SymbolLibrary([HIER_FIXTURES])
        sch = Schematic.new()
        with pytest.raises(ValueError, match="not found"):
            sch.pin_position("NOPE", "P", libs)

    def test_pin_position_missing_pin(self):
        libs = SymbolLibrary([HIER_FIXTURES])
        sch = Schematic.from_text(
            "v {xschem version=3.4.5 file_version=1.2}\n"
            "G {}\nK {}\nV {}\nS {}\nE {}\n"
            "C {resistor.sym} 200 -100 0 0 {name=R1 value=10k}\n"
        )
        with pytest.raises(ValueError, match="Pin 'Z' not found"):
            sch.pin_position("R1", "Z", libs)

    def test_pin_position_missing_symbol(self):
        libs = SymbolLibrary([HIER_FIXTURES])
        sch = Schematic.from_text(
            "v {xschem version=3.4.5 file_version=1.2}\n"
            "G {}\nK {}\nV {}\nS {}\nE {}\n"
            "C {nonexistent.sym} 200 -100 0 0 {name=R1}\n"
        )
        with pytest.raises(ValueError, match="Cannot resolve"):
            sch.pin_position("R1", "P", libs)


class TestConnect:
    def test_connect_places_lab_pin_at_target(self):
        libs = SymbolLibrary([HIER_FIXTURES])
        sch = Schematic.from_text(
            "v {xschem version=3.4.5 file_version=1.2}\n"
            "G {}\nK {}\nV {}\nS {}\nE {}\n"
            "C {resistor.sym} 200 -100 0 0 {name=R1 value=10k}\n"
        )
        before = len(sch.components)
        comp = sch.connect("R1", "P", "VDD", libs)
        assert comp.symbol == "lab_pin.sym"
        assert comp.attributes.get("lab") == "VDD"
        assert (comp.x, comp.y) == (200, -130)
        assert len(sch.components) == before + 1

    def test_connect_missing_component(self):
        libs = SymbolLibrary([HIER_FIXTURES])
        sch = Schematic.new()
        with pytest.raises(ValueError, match="not found"):
            sch.connect("NOPE", "P", "VDD", libs)

    def test_connect_missing_pin(self):
        libs = SymbolLibrary([HIER_FIXTURES])
        sch = Schematic.from_text(
            "v {xschem version=3.4.5 file_version=1.2}\n"
            "G {}\nK {}\nV {}\nS {}\nE {}\n"
            "C {resistor.sym} 200 -100 0 0 {name=R1 value=10k}\n"
        )
        with pytest.raises(ValueError, match="Pin 'Z' not found"):
            sch.connect("R1", "Z", "VDD", libs)

    def test_connect_multiple_pins_unique_names(self):
        libs = SymbolLibrary([HIER_FIXTURES])
        sch = Schematic.from_text(
            "v {xschem version=3.4.5 file_version=1.2}\n"
            "G {}\nK {}\nV {}\nS {}\nE {}\n"
            "C {resistor.sym} 200 -100 0 0 {name=R1 value=10k}\n"
        )
        a = sch.connect("R1", "P", "VDD", libs)
        b = sch.connect("R1", "M", "GND", libs)
        labs = [c for c in sch.components if c.symbol == "lab_pin.sym"]
        assert len(labs) == 2
        assert {c.attributes.get("lab") for c in labs} == {"GND", "VDD"}
        # Auto-generated names must be unique
        assert a.name != b.name


class TestPinErrorMessages:
    def test_case_insensitive_suggestion(self):
        libs = SymbolLibrary([HIER_FIXTURES])
        sch = Schematic.from_text(
            "v {xschem version=3.4.5 file_version=1.2}\n"
            "G {}\nK {}\nV {}\nS {}\nE {}\n"
            "C {resistor.sym} 200 -100 0 0 {name=R1 value=10k}\n"
        )
        with pytest.raises(ValueError, match="did you mean 'P'"):
            sch.pin_position("R1", "p", libs)

    def test_error_includes_rotation(self):
        libs = SymbolLibrary([HIER_FIXTURES])
        sch = Schematic.from_text(
            "v {xschem version=3.4.5 file_version=1.2}\n"
            "G {}\nK {}\nV {}\nS {}\nE {}\n"
            "C {resistor.sym} 200 -100 1 0 {name=R1 value=10k}\n"
        )
        with pytest.raises(ValueError, match="rotation=1"):
            sch.pin_position("R1", "ZZZ", libs)


class TestAddWire:
    def test_horizontal_wire_between_pins(self):
        libs = SymbolLibrary([HIER_FIXTURES])
        sch = Schematic.from_text(
            "v {xschem version=3.4.5 file_version=1.2}\n"
            "G {}\nK {}\nV {}\nS {}\nE {}\n"
            "C {resistor.sym} 200 -100 1 0 {name=R1 value=10k}\n"
            "C {resistor.sym} 400 -100 1 0 {name=R2 value=10k}\n"
        )
        net = sch.add_wire("R1", "P", "R2", "M", libs)
        assert net.x1 != net.x2 or net.y1 != net.y2
        assert net.y1 == net.y2  # horizontal

    def test_diagonal_pins_rejected(self):
        libs = SymbolLibrary([HIER_FIXTURES])
        sch = Schematic.from_text(
            "v {xschem version=3.4.5 file_version=1.2}\n"
            "G {}\nK {}\nV {}\nS {}\nE {}\n"
            "C {resistor.sym} 200 -100 0 0 {name=R1}\n"
            "C {resistor.sym} 400 -300 0 0 {name=R2}\n"
        )
        with pytest.raises(ValueError, match="orthogonally aligned"):
            sch.add_wire("R1", "P", "R2", "M", libs)


class TestAddLabelPinAlias:
    def test_alias_creates_lab_pin(self):
        libs = SymbolLibrary([HIER_FIXTURES])
        sch = Schematic.from_text(
            "v {xschem version=3.4.5 file_version=1.2}\n"
            "G {}\nK {}\nV {}\nS {}\nE {}\n"
            "C {resistor.sym} 200 -100 0 0 {name=R1 value=10k}\n"
        )
        comp = sch.add_label_pin("R1", "P", "VDD", libs)
        assert comp.symbol.endswith("lab_pin.sym")
        assert comp.attributes.get("lab") == "VDD"


class TestConnectLabPinResolution:
    def test_no_lab_pin_in_library_raises(self, tmp_path):
        # SymbolLibrary that contains a resistor but no lab_pin → must raise.
        lib_dir = tmp_path / "lib_only_res"
        lib_dir.mkdir()
        (lib_dir / "res.sym").write_text(
            "v {xschem version=3.4.5 file_version=1.2}\n"
            "G {}\n"
            'K {type=resistor template="name=R1 value=1k"}\n'
            "V {}\nS {}\nE {}\n"
            "B 5 -2.5 -32.5 2.5 -27.5 {name=P dir=inout}\n"
            "B 5 -2.5 27.5 2.5 32.5 {name=M dir=inout}\n"
        )
        libs = SymbolLibrary([lib_dir])
        sch = Schematic.new()
        sch.add_component(
            "res.sym", 100, -100, attributes={"name": "R1", "value": "1k"}
        )
        with pytest.raises(ValueError, match="lab_pin"):
            sch.connect("R1", "P", "VDD", libs)

    def test_fractional_pin_coordinate_preserved(self):
        libs = SymbolLibrary([HIER_FIXTURES])
        sch = Schematic.new()
        # Component anchor at fractional coordinates → lab_pin must
        # land exactly on the pin, not be truncated to int.
        sch.add_component(
            "resistor.sym", 102.5, -107.5, attributes={"name": "R1", "value": "1k"}
        )
        comp = sch.connect("R1", "P", "VDD", libs)
        # resistor.sym pin P is at (0, -30); anchor (102.5, -107.5) +
        # rotation 0 → (102.5, -137.5).
        assert (comp.x, comp.y) == (102.5, -137.5)


class TestCaseInsensitivePinLookup:
    def test_off_case_resolves_when_opted_in(self):
        libs = SymbolLibrary([HIER_FIXTURES])
        sch = Schematic.from_text(
            "v {xschem version=3.4.5 file_version=1.2}\n"
            "G {}\nK {}\nV {}\nS {}\nE {}\n"
            "C {resistor.sym} 200 -100 0 0 {name=R1 value=10k}\n"
        )
        # resistor.sym uses uppercase P/M.
        pos = sch.pin_position("R1", "p", libs, case_insensitive=True)
        assert pos == (200, -130)

    def test_off_case_rejected_by_default(self):
        libs = SymbolLibrary([HIER_FIXTURES])
        sch = Schematic.from_text(
            "v {xschem version=3.4.5 file_version=1.2}\n"
            "G {}\nK {}\nV {}\nS {}\nE {}\n"
            "C {resistor.sym} 200 -100 0 0 {name=R1 value=10k}\n"
        )
        with pytest.raises(ValueError, match="did you mean 'P'"):
            sch.pin_position("R1", "p", libs)

    def test_case_insensitive_propagates_to_connect(self):
        libs = SymbolLibrary([HIER_FIXTURES])
        sch = Schematic.from_text(
            "v {xschem version=3.4.5 file_version=1.2}\n"
            "G {}\nK {}\nV {}\nS {}\nE {}\n"
            "C {resistor.sym} 200 -100 0 0 {name=R1 value=10k}\n"
        )
        comp = sch.connect("R1", "p", "VDD", libs, case_insensitive=True)
        assert comp.attributes.get("lab") == "VDD"

    def test_case_insensitive_propagates_to_add_wire(self):
        libs = SymbolLibrary([HIER_FIXTURES])
        sch = Schematic.from_text(
            "v {xschem version=3.4.5 file_version=1.2}\n"
            "G {}\nK {}\nV {}\nS {}\nE {}\n"
            "C {resistor.sym} 200 -100 0 0 {name=R1}\n"
            "C {resistor.sym} 400 -100 0 0 {name=R2}\n"
        )
        net = sch.add_wire("R1", "p", "R2", "p", libs, case_insensitive=True)
        assert net.y1 == net.y2

    def test_pin_error_includes_rotation(self):
        libs = SymbolLibrary([HIER_FIXTURES])
        sch = Schematic.from_text(
            "v {xschem version=3.4.5 file_version=1.2}\n"
            "G {}\nK {}\nV {}\nS {}\nE {}\n"
            "C {resistor.sym} 200 -100 1 0 {name=R1 value=10k}\n"
        )
        with pytest.raises(ValueError, match="rotation=1"):
            sch.pin_position("R1", "ZZZ", libs)
