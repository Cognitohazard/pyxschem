"""Tests for xschem .sym symbol file support."""

from pathlib import Path

import pytest

from pyxschem import Pin, Symbol
from pyxschem.model import RawLine
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
        sym = Symbol.from_text("v {xschem version=3.4.5 file_version=1.2}\nG {}\nK {}\nV {}\nS {}\nE {}\n")
        assert sym.type is None
        assert sym.format is None
        assert sym.template == {}


class TestSymbolFromText:
    def test_from_text(self):
        text = (SYM_FIXTURES / "res.sym").read_text()
        sym = Symbol.from_text(text)
        assert sym.type == "resistor"
        assert len(sym.pins) == 2


class TestExports:
    def test_import_symbol(self):
        from pyxschem import Symbol, Pin
        assert Symbol is not None
        assert Pin is not None
