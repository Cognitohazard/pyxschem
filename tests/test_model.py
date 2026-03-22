"""Tests for pyxschem data model."""

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


class TestComponent:
    def test_to_line_generates_correct_format(self):
        c = Component(
            symbol="devices/res.sym",
            x=300,
            y=-200,
            rotation=0,
            mirror=0,
            attributes={"name": "R1", "value": "10k", "m": "1"},
        )
        assert c.to_line() == "C {devices/res.sym} 300 -200 0 0 {name=R1 value=10k m=1}"

    def test_raw_line_preserved_when_unmodified(self):
        original = "C {devices/res.sym} 300 -200 0 0 {name=R1 value=10k m=1}"
        c = Component(
            symbol="devices/res.sym",
            x=300,
            y=-200,
            rotation=0,
            mirror=0,
            attributes={"name": "R1", "value": "10k", "m": "1"},
            raw_line=original,
        )
        assert c.to_line() == original

    def test_raw_line_cleared_on_set_attribute(self):
        original = "C {devices/res.sym} 300 -200 0 0 {name=R1 value=10k}"
        c = Component(
            symbol="devices/res.sym",
            x=300,
            y=-200,
            rotation=0,
            mirror=0,
            attributes={"name": "R1", "value": "10k"},
            raw_line=original,
        )
        c.set_attribute("value", "4.7k")
        assert c.to_line() != original
        assert "4.7k" in c.to_line()
        assert c.raw_line is None

    def test_name_and_value_properties(self):
        c = Component(
            symbol="devices/res.sym",
            x=0,
            y=0,
            rotation=0,
            mirror=0,
            attributes={"name": "R1", "value": "10k"},
        )
        assert c.name == "R1"
        assert c.value == "10k"

    def test_name_property_missing(self):
        c = Component(
            symbol="devices/res.sym",
            x=0,
            y=0,
            rotation=0,
            mirror=0,
        )
        assert c.name is None
        assert c.value is None

    def test_empty_attributes(self):
        c = Component(
            symbol="devices/gnd.sym",
            x=160,
            y=-70,
            rotation=0,
            mirror=0,
        )
        assert c.to_line() == "C {devices/gnd.sym} 160 -70 0 0 {}"

    def test_attributes_with_spaces_are_braced(self):
        c = Component(
            symbol="devices/vsource.sym",
            x=0,
            y=0,
            rotation=0,
            mirror=0,
            attributes={"name": "V1", "value": "PWL(0 0 1n 1.8)"},
        )
        line = c.to_line()
        assert "value={PWL(0 0 1n 1.8)}" in line


class TestNet:
    def test_to_line_with_label(self):
        n = Net(x1=160, y1=-160, x2=160, y2=-200, attributes={"lab": "VDD"})
        assert n.to_line() == "N 160 -160 160 -200 {lab=VDD}"

    def test_to_line_unlabeled(self):
        n = Net(x1=300, y1=-160, x2=300, y2=-200)
        assert n.to_line() == "N 300 -160 300 -200 {}"

    def test_label_property(self):
        n = Net(x1=0, y1=0, x2=100, y2=0, attributes={"lab": "VDD"})
        assert n.label == "VDD"

    def test_label_property_missing(self):
        n = Net(x1=0, y1=0, x2=100, y2=0)
        assert n.label is None

    def test_raw_line_preserved(self):
        original = "N 160 -160 160 -200 {lab=VDD}"
        n = Net(
            x1=160,
            y1=-160,
            x2=160,
            y2=-200,
            attributes={"lab": "VDD"},
            raw_line=original,
        )
        assert n.to_line() == original


class TestText:
    def test_to_line(self):
        t = Text(
            text="My Label",
            x=100,
            y=-400,
            rotation=0,
            mirror=0,
            xscale=0.3,
            yscale=0.3,
        )
        assert t.to_line() == "T {My Label} 100 -400 0 0 0.3 0.3 {}"

    def test_raw_line_preserved(self):
        original = "T {My Label} 100 -400 0 0 0.3 0.3 {}"
        t = Text(
            text="My Label",
            x=100,
            y=-400,
            rotation=0,
            mirror=0,
            xscale=0.3,
            yscale=0.3,
            raw_line=original,
        )
        assert t.to_line() == original


class TestGraphicLine:
    def test_to_line(self):
        gl = GraphicLine(layer=4, x1=0, y1=0, x2=100, y2=100)
        assert gl.to_line() == "L 4 0 0 100 100 {}"

    def test_raw_line_preserved(self):
        original = "L 4 0 0 100 100 {}"
        gl = GraphicLine(layer=4, x1=0, y1=0, x2=100, y2=100, raw_line=original)
        assert gl.to_line() == original


class TestBox:
    def test_to_line(self):
        b = Box(layer=4, x1=0, y1=0, x2=200, y2=100)
        assert b.to_line() == "B 4 0 0 200 100 {}"

    def test_raw_line_preserved(self):
        original = "B 4 0 0 200 100 {dash=4}"
        b = Box(
            layer=4,
            x1=0,
            y1=0,
            x2=200,
            y2=100,
            attributes={"dash": "4"},
            raw_line=original,
        )
        assert b.to_line() == original


class TestArc:
    def test_to_line(self):
        a = Arc(layer=4, x=100, y=100, r=50.0, start_angle=0.0, sweep_angle=360.0)
        assert a.to_line() == "A 4 100 100 50 0 360 {}"

    def test_raw_line_preserved(self):
        original = "A 4 100 100 50 0 360 {}"
        a = Arc(
            layer=4,
            x=100,
            y=100,
            r=50.0,
            start_angle=0.0,
            sweep_angle=360.0,
            raw_line=original,
        )
        assert a.to_line() == original


class TestPolygon:
    def test_to_line(self):
        p = Polygon(layer=4, points=[(0, 0), (100, 0), (50, 100)])
        assert p.to_line() == "P 4 3 0 0 100 0 50 100 {}"

    def test_raw_line_preserved(self):
        original = "P 4 3 0 0 100 0 50 100 {}"
        p = Polygon(layer=4, points=[(0, 0), (100, 0), (50, 100)], raw_line=original)
        assert p.to_line() == original


class TestHeader:
    def test_to_lines_preserves_raw(self):
        lines = [
            "v {xschem version=3.4.5 file_version=1.2}",
            "G {}",
            "K {}",
            "V {}",
            "S {}",
            "E {}",
        ]
        h = Header(raw_lines=lines)
        assert h.to_lines() == lines

    def test_empty_header(self):
        h = Header()
        assert h.to_lines() == []


class TestRawLine:
    def test_preserves_unknown_line(self):
        line = "Z some_future_type 1 2 3 {}"
        r = RawLine(line=line)
        assert r.to_line() == line
