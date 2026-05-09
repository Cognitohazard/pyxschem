"""Tests for xschem .sym symbol file support."""

from pathlib import Path

import pytest

from pyxschem import Symbol
from pyxschem.model import Box, RawLine
from pyxschem.parser import parse_schematic, serialize_schematic

SYM_FIXTURES = Path(__file__).parent / "fixtures" / "real" / "sym"
SYM_FILES = sorted(SYM_FIXTURES.glob("*.sym"))


@pytest.fixture(params=SYM_FILES, ids=lambda p: p.name)
def sym_file(request):
    return request.param


class TestSymLoading:
    def test_loads_without_error(self, sym_file):
        sym = Symbol.load(sym_file)
        assert sym.header is not None

    def test_no_rawline_fallbacks(self, sym_file):
        text = sym_file.read_text()
        elements = parse_schematic(text)
        raw = [e for e in elements if isinstance(e, RawLine) and e.line.strip()]
        assert raw == [], f"Unexpected RawLine: {[r.line for r in raw]}"

    def test_round_trip_byte_identical(self, sym_file):
        text = sym_file.read_text()
        elements = parse_schematic(text)
        assert serialize_schematic(elements) == text


class TestPinExtraction:
    def test_res_pins(self):
        sym = Symbol.load(SYM_FIXTURES / "res.sym")
        pins = sym.pins
        assert len(pins) == 2
        assert pins[0].name == "P"
        assert pins[0].direction == "inout"
        assert pins[1].name == "M"
        assert pins[1].direction == "inout"

    def test_nmos4_pins(self):
        sym = Symbol.load(SYM_FIXTURES / "nmos4.sym")
        pins = sym.pins
        assert len(pins) == 4
        names = [(p.name, p.direction) for p in pins]
        assert names == [("d", "inout"), ("g", "in"), ("s", "inout"), ("b", "in")]

    def test_vsource_pins(self):
        sym = Symbol.load(SYM_FIXTURES / "vsource.sym")
        pins = sym.pins
        assert len(pins) == 2
        assert pins[0].name == "p"
        assert pins[1].name == "m"

    def test_lab_pin_single_pin(self):
        sym = Symbol.load(SYM_FIXTURES / "lab_pin.sym")
        pins = sym.pins
        assert len(pins) == 1
        assert pins[0].name == "p"
        assert pins[0].direction == "in"

    def test_pin_positions_are_float(self):
        sym = Symbol.load(SYM_FIXTURES / "res.sym")
        for pin in sym.pins:
            assert isinstance(pin.x, float)
            assert isinstance(pin.y, float)


class TestMetadata:
    def test_res_type(self):
        sym = Symbol.load(SYM_FIXTURES / "res.sym")
        assert sym.type == "resistor"

    def test_res_format(self):
        sym = Symbol.load(SYM_FIXTURES / "res.sym")
        assert sym.format == "@name @pinlist @value m=@m"

    def test_res_template(self):
        sym = Symbol.load(SYM_FIXTURES / "res.sym")
        t = sym.template
        assert t["name"] == "R1"
        assert t["value"] == "1k"
        assert t["m"] == "1"
        assert "footprint" in t
        assert "device" in t

    def test_nmos4_type(self):
        sym = Symbol.load(SYM_FIXTURES / "nmos4.sym")
        assert sym.type == "nmos"

    def test_nmos4_format_has_model(self):
        sym = Symbol.load(SYM_FIXTURES / "nmos4.sym")
        assert "@model" in sym.format

    def test_no_k_block_returns_none(self):
        """Symbol with empty K block returns None for type/format."""
        sym = Symbol.from_text(
            "v {xschem version=3.4.5 file_version=1.2}\nG {}\nK {}\nV {}\nS {}\nE {}\n"
        )
        assert sym.type is None
        assert sym.format is None
        assert sym.template == {}


class TestSymbolFromText:
    def test_from_text(self):
        text = (SYM_FIXTURES / "res.sym").read_text()
        sym = Symbol.from_text(text)
        assert sym.type == "resistor"
        assert len(sym.pins) == 2


class TestSymbolMutation:
    def test_new_has_default_symbol_header(self):
        sym = Symbol.new()
        assert sym.header is not None
        assert sym.header.raw_lines == [
            "v {xschem version=3.4.5 file_version=1.2}",
            "G {}",
            "K {}",
            "V {}",
            "S {}",
            "F {}",
            "E {}",
        ]

    def test_set_version_updates_header(self):
        sym = Symbol.new()
        sym.set_version("9.9.9", "2.0")
        assert sym.header.raw_lines[0] == "v {xschem version=9.9.9 file_version=2.0}"

    def test_set_version_creates_header_when_missing(self):
        sym = Symbol.from_text("B 5 -1 -1 1 1 {name=p dir=in}\n")
        assert sym.header is None
        sym.set_version("9.9.9", "2.0")
        assert sym.header is not None
        assert sym.header.raw_lines[0] == "v {xschem version=9.9.9 file_version=2.0}"

    def test_add_pin_returns_box_and_updates_pins(self):
        sym = Symbol.new()
        pin_box = sym.add_pin("p", "in", 10, 20)
        assert isinstance(pin_box, Box)
        assert len(sym.pins) == 1
        assert sym.pins[0].name == "p"
        assert sym.pins[0].direction == "in"
        assert sym.pins[0].x == 10
        assert sym.pins[0].y == 20

    def test_add_text_serializes(self):
        sym = Symbol.new()
        sym.add_text("@name", 5, 10)
        assert "T {@name} 5 10 0 0 0.2 0.2 {}" in sym.to_text()

    def test_add_graphics_and_accessors(self):
        sym = Symbol.new()
        line = sym.add_line(4, 0, 0, 10, 10)
        box = sym.add_box(4, 0, 0, 20, 10)
        arc = sym.add_arc(4, 10, 10, 5, 0, 180)
        polygon = sym.add_polygon(4, [(0, 0), (10, 0), (5, 5)])

        # Accessor properties (inherited from mixin)
        assert line in sym.lines
        assert box in sym.boxes
        assert arc in sym.arcs
        assert polygon in sym.polygons

        # Serialization
        text = sym.to_text()
        assert "L 4 0 0 10 10 {}" in text
        assert "B 4 0 0 20 10 {}" in text
        assert "A 4 10 10 5 0 180 {}" in text
        assert "P 4 3 0 0 10 0 5 5 {}" in text

    def test_texts_accessor(self):
        sym = Symbol.new()
        t = sym.add_text("@name", 5, 10)
        assert t in sym.texts

    def test_save_round_trip(self, tmp_path):
        sym = Symbol.new()
        sym.add_pin("p", "inout", 0, 0)
        sym.add_text("@name", 5, 10)

        out = tmp_path / "generated.sym"
        sym.save(out)

        reloaded = Symbol.load(out)
        assert len(reloaded.pins) == 1
        assert reloaded.pins[0].name == "p"

    def test_save_no_path_on_new_raises(self):
        sym = Symbol.new()
        with pytest.raises(ValueError, match="No path"):
            sym.save()


class TestSymbolBBox:
    """Test bbox computation via bbox_from_elements on symbol elements."""

    def test_bbox_from_lines(self):
        from pyxschem.geometry import bbox_from_elements

        sym = Symbol.new()
        sym.add_line(4, -10, -20, 10, 20)
        bb = bbox_from_elements(sym.elements)
        assert bb is not None
        assert bb.x1 == -10
        assert bb.y1 == -20
        assert bb.x2 == 10
        assert bb.y2 == 20

    def test_bbox_excludes_pin_layer(self):
        from pyxschem.geometry import bbox_from_elements

        sym = Symbol.new()
        sym.add_line(4, 0, 0, 10, 10)
        sym.add_pin("p", "in", 100, 100)  # layer 5 — should be excluded
        bb = bbox_from_elements(sym.elements)
        assert bb is not None
        assert bb.x2 == 10  # not 100

    def test_bbox_none_for_empty(self):
        from pyxschem.geometry import bbox_from_elements

        sym = Symbol.new()
        assert bbox_from_elements(sym.elements) is None

    def test_bbox_none_for_pins_only(self):
        from pyxschem.geometry import bbox_from_elements

        sym = Symbol.new()
        sym.add_pin("p", "in", 10, 10)
        assert bbox_from_elements(sym.elements) is None

    def test_bbox_real_res_symbol(self):
        from pyxschem.geometry import bbox_from_elements

        sym = Symbol.load(SYM_FIXTURES / "res.sym")
        bb = bbox_from_elements(sym.elements)
        assert bb is not None
        assert bb.width > 0
        assert bb.height > 0

    def test_bbox_with_arc(self):
        from pyxschem.geometry import bbox_from_elements

        sym = Symbol.new()
        sym.add_arc(4, 50, 50, 10, 0, 360)
        bb = bbox_from_elements(sym.elements)
        assert bb is not None
        assert bb.x1 == 40
        assert bb.y1 == 40
        assert bb.x2 == 60
        assert bb.y2 == 60

    def test_bbox_with_polygon(self):
        from pyxschem.geometry import bbox_from_elements

        sym = Symbol.new()
        sym.add_polygon(4, [(0, 0), (10, 5), (5, 15)])
        bb = bbox_from_elements(sym.elements)
        assert bb is not None
        assert bb.x1 == 0
        assert bb.y1 == 0
        assert bb.x2 == 10
        assert bb.y2 == 15


class TestPinSide:
    def _two_pin_symbol(self) -> Symbol:
        sym = Symbol.new()
        sym.add_box(layer=4, x1=-10, y1=-25, x2=10, y2=25)  # body
        sym.add_pin("P", "in", 0, -30)  # top
        sym.add_pin("M", "out", 0, 30)  # bottom
        return sym

    def test_local_default_rotation(self):
        sym = self._two_pin_symbol()
        assert sym.pin_side("P") == "up"
        assert sym.pin_side("M") == "down"

    def test_rotation_swaps_to_horizontal(self):
        sym = self._two_pin_symbol()
        # P sits on the "up" side; rotating maps up→right→down→left.
        assert sym.pin_side("P", rotation=1) == "right"
        assert sym.pin_side("P", rotation=2) == "down"
        assert sym.pin_side("P", rotation=3) == "left"
        # M sits on the "down" side; opposite cycle.
        assert sym.pin_side("M", rotation=1) == "left"

    def test_case_insensitive(self):
        sym = self._two_pin_symbol()
        with pytest.raises(ValueError):
            sym.pin_side("p")
        assert sym.pin_side("p", case_insensitive=True) == "up"

    def test_unknown_pin_raises(self):
        sym = self._two_pin_symbol()
        with pytest.raises(ValueError):
            sym.pin_side("Z")


class TestExports:
    def test_import_symbol(self):
        from pyxschem import Pin, Symbol

        assert Symbol is not None
        assert Pin is not None
