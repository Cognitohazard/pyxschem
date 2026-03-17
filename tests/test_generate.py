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
    def test_connect_creates_labeled_net(self):
        libs = SymbolLibrary([HIER_FIXTURES])
        sch = Schematic.from_text(
            "v {xschem version=3.4.5 file_version=1.2}\n"
            "G {}\nK {}\nV {}\nS {}\nE {}\n"
            "C {resistor.sym} 200 -100 0 0 {name=R1 value=10k}\n"
        )
        net = sch.connect("R1", "P", "VDD", libs)
        assert net.label == "VDD"
        assert net.x1 == 200.0
        assert net.y1 == -130.0
        assert len(sch.nets) == 1

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

    def test_connect_multiple_pins(self):
        libs = SymbolLibrary([HIER_FIXTURES])
        sch = Schematic.from_text(
            "v {xschem version=3.4.5 file_version=1.2}\n"
            "G {}\nK {}\nV {}\nS {}\nE {}\n"
            "C {resistor.sym} 200 -100 0 0 {name=R1 value=10k}\n"
        )
        sch.connect("R1", "P", "VDD", libs)
        sch.connect("R1", "M", "GND", libs)
        assert len(sch.nets) == 2
        labels = sorted(n.label for n in sch.nets)
        assert labels == ["GND", "VDD"]
