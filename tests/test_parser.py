"""Tests for xschem parser and round-trip serialization."""

from pathlib import Path

from pyxschem.model import (
    Arc,
    Box,
    Component,
    GraphicLine,
    Header,
    Net,
    Polygon,
    RawLine,
    Text,
)
from pyxschem.parser import parse_schematic, serialize_schematic

FIXTURES = Path(__file__).parent / "fixtures"


class TestParseIndividualLines:
    def test_component_line(self):
        elements = parse_schematic("C {devices/res.sym} 300 -200 0 0 {name=R1 value=10k}\n")
        assert len(elements) == 1
        c = elements[0]
        assert isinstance(c, Component)
        assert c.symbol == "devices/res.sym"
        assert c.x == 300
        assert c.y == -200
        assert c.rotation == 0
        assert c.mirror == 0
        assert c.attributes == {"name": "R1", "value": "10k"}
        assert c.raw_line is not None

    def test_net_line_with_label(self):
        elements = parse_schematic("N 160 -160 160 -200 {lab=VDD}\n")
        assert len(elements) == 1
        n = elements[0]
        assert isinstance(n, Net)
        assert n.x1 == 160
        assert n.y1 == -160
        assert n.x2 == 160
        assert n.y2 == -200
        assert n.label == "VDD"

    def test_net_line_empty_attrs(self):
        elements = parse_schematic("N 300 -160 300 -200 {}\n")
        n = elements[0]
        assert isinstance(n, Net)
        assert n.attributes == {}

    def test_text_line(self):
        elements = parse_schematic("T {My Label} 100 -400 0 0 0.3 0.3 {}\n")
        t = elements[0]
        assert isinstance(t, Text)
        assert t.text == "My Label"
        assert t.x == 100
        assert t.y == -400
        assert t.xscale == 0.3
        assert t.yscale == 0.3

    def test_graphic_line(self):
        elements = parse_schematic("L 4 50 -350 400 -350 {}\n")
        gl = elements[0]
        assert isinstance(gl, GraphicLine)
        assert gl.layer == 4
        assert gl.x1 == 50
        assert gl.y2 == -350

    def test_box_line(self):
        elements = parse_schematic("B 5 40 -420 410 -60 {dash=4}\n")
        b = elements[0]
        assert isinstance(b, Box)
        assert b.layer == 5
        assert b.attributes == {"dash": "4"}

    def test_arc_line(self):
        elements = parse_schematic("A 4 200 -150 50 0 360 {}\n")
        a = elements[0]
        assert isinstance(a, Arc)
        assert a.layer == 4
        assert a.r == 50.0
        assert a.sweep_angle == 360.0

    def test_polygon_line(self):
        elements = parse_schematic("P 4 3 500 -100 600 -100 550 -200 {}\n")
        p = elements[0]
        assert isinstance(p, Polygon)
        assert p.layer == 4
        assert p.points == [(500, -100), (600, -100), (550, -200)]

    def test_unknown_line_becomes_rawline(self):
        elements = parse_schematic("Z some_future 1 2 3\n")
        assert isinstance(elements[0], RawLine)
        assert elements[0].line == "Z some_future 1 2 3"


class TestParseHeader:
    def test_header_parsed(self):
        text = "v {xschem version=3.4.5 file_version=1.2}\nG {}\nK {}\nV {}\nS {}\nE {}\n"
        elements = parse_schematic(text)
        assert len(elements) == 1
        h = elements[0]
        assert isinstance(h, Header)
        assert len(h.raw_lines) == 6
        assert h.raw_lines[0] == "v {xschem version=3.4.5 file_version=1.2}"

    def test_header_only_file(self):
        text = "v {xschem version=3.4.5 file_version=1.2}\nG {}\nK {}\nV {}\nS {}\nE {}\n"
        elements = parse_schematic(text)
        assert len(elements) == 1
        assert isinstance(elements[0], Header)


class TestParseFullFile:
    def test_simple_fixture(self):
        text = (FIXTURES / "simple.sch").read_text()
        elements = parse_schematic(text)
        assert len(elements) == 12
        assert isinstance(elements[0], Header)
        types = [type(e).__name__ for e in elements[1:]]
        assert types == [
            "Component", "Component", "Component",
            "Net", "Net", "Net",
            "Text", "GraphicLine", "Box", "Arc", "Polygon",
        ]

    def test_all_elements_have_raw_line(self):
        text = (FIXTURES / "simple.sch").read_text()
        elements = parse_schematic(text)
        for e in elements:
            if isinstance(e, Header):
                assert len(e.raw_lines) > 0
            else:
                assert e.raw_line is not None


class TestMultiline:
    def test_multiline_attributes(self):
        text = (FIXTURES / "multiline.sch").read_text()
        elements = parse_schematic(text)

        # Header + Component + Net = 3
        components = [e for e in elements if isinstance(e, Component)]
        assert len(components) == 1
        c = components[0]
        assert c.symbol == "devices/nmos.sym"
        assert c.attributes["name"] == "M1"
        assert c.attributes["W"] == "1"
        assert c.attributes["nf"] == "1"

    def test_multiline_raw_line_preserved(self):
        text = (FIXTURES / "multiline.sch").read_text()
        elements = parse_schematic(text)
        components = [e for e in elements if isinstance(e, Component)]
        c = components[0]
        # raw_line should contain the full multiline block
        assert "\n" in c.raw_line


class TestRoundTrip:
    def test_simple_fixture_round_trip(self):
        text = (FIXTURES / "simple.sch").read_text()
        elements = parse_schematic(text)
        result = serialize_schematic(elements)
        assert result == text, f"Round-trip failed:\n---EXPECTED---\n{text}\n---GOT---\n{result}"

    def test_multiline_fixture_round_trip(self):
        text = (FIXTURES / "multiline.sch").read_text()
        elements = parse_schematic(text)
        result = serialize_schematic(elements)
        assert result == text

    def test_empty_input(self):
        assert parse_schematic("") == []
        assert serialize_schematic([]) == ""

    def test_header_only_round_trip(self):
        text = "v {xschem version=3.4.5 file_version=1.2}\nG {}\nK {}\nV {}\nS {}\nE {}\n"
        elements = parse_schematic(text)
        result = serialize_schematic(elements)
        assert result == text

    def test_trailing_newline_preserved(self):
        text = "N 0 0 100 0 {}\n"
        result = serialize_schematic(parse_schematic(text))
        assert result.endswith("\n")


class TestEdgeCases:
    def test_component_raw_line_used_for_round_trip(self):
        """Verify raw_line (not regenerated fields) is used in serialize."""
        line = "C {devices/res.sym} 300 -200 0 0 {name=R1 value=10k m=1}"
        text = line + "\n"
        elements = parse_schematic(text)
        result = serialize_schematic(elements)
        assert result == text
