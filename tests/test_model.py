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

    def test_mark_dirty_clears_raw_line(self):
        c = Component(
            symbol="devices/res.sym",
            x=0,
            y=0,
            rotation=0,
            mirror=0,
            raw_line="C {devices/res.sym} 0 0 0 0 {}",
        )
        c.mark_dirty()
        assert c.raw_line is None

    def test_field_assignment_auto_dirties(self):
        c = Component(
            symbol="devices/res.sym",
            x=0,
            y=0,
            rotation=0,
            mirror=0,
            raw_line="C {devices/res.sym} 0 0 0 0 {}",
        )
        c.x = 100
        assert c.raw_line is None
        assert "100" in c.to_line()


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

    def test_set_attribute_clears_raw_line(self):
        n = Net(x1=0, y1=0, x2=100, y2=0, raw_line="N 0 0 100 0 {}")
        n.set_attribute("lab", "VDD")
        assert n.raw_line is None
        assert "lab=VDD" in n.to_line()

    def test_mark_dirty_clears_raw_line(self):
        n = Net(x1=0, y1=0, x2=100, y2=0, raw_line="N 0 0 100 0 {}")
        n.mark_dirty()
        assert n.raw_line is None

    def test_field_assignment_auto_dirties(self):
        n = Net(x1=0, y1=0, x2=100, y2=0, raw_line="N 0 0 100 0 {}")
        n.x2 = 150
        assert n.raw_line is None
        assert n.to_line() == "N 0 0 150 0 {}"

    def test_dict_mutation_auto_dirties(self):
        n = Net(x1=0, y1=0, x2=100, y2=0, raw_line="N 0 0 100 0 {}")
        n.attributes["lab"] = "VDD"
        assert n.raw_line is None
        assert "lab=VDD" in n.to_line()

    def test_dict_update_auto_dirties(self):
        n = Net(x1=0, y1=0, x2=100, y2=0, raw_line="N 0 0 100 0 {}")
        n.attributes.update({"lab": "GND"})
        assert n.raw_line is None

    def test_dict_pop_auto_dirties(self):
        n = Net(
            x1=0, y1=0, x2=100, y2=0,
            attributes={"lab": "VDD"},
            raw_line="N 0 0 100 0 {lab=VDD}",
        )
        n.attributes.pop("lab")
        assert n.raw_line is None

    def test_dict_pop_missing_key_does_not_dirty(self):
        n = Net(x1=0, y1=0, x2=100, y2=0, raw_line="N 0 0 100 0 {}")
        n.attributes.pop("nonexistent", None)
        assert n.raw_line is not None

    def test_dict_clear_auto_dirties(self):
        n = Net(
            x1=0, y1=0, x2=100, y2=0,
            attributes={"lab": "VDD"},
            raw_line="N 0 0 100 0 {lab=VDD}",
        )
        n.attributes.clear()
        assert n.raw_line is None

    def test_dict_setdefault_new_key_auto_dirties(self):
        n = Net(x1=0, y1=0, x2=100, y2=0, raw_line="N 0 0 100 0 {}")
        n.attributes.setdefault("lab", "VDD")
        assert n.raw_line is None

    def test_dict_setdefault_existing_key_does_not_dirty(self):
        n = Net(
            x1=0, y1=0, x2=100, y2=0,
            attributes={"lab": "VDD"},
            raw_line="N 0 0 100 0 {lab=VDD}",
        )
        n.attributes.setdefault("lab", "GND")
        assert n.raw_line is not None


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

    def test_set_attribute_clears_raw_line(self):
        t = Text(
            text="My Label",
            x=100,
            y=-400,
            rotation=0,
            mirror=0,
            xscale=0.3,
            yscale=0.3,
            raw_line="T {My Label} 100 -400 0 0 0.3 0.3 {}",
        )
        t.set_attribute("layer", "4")
        assert t.raw_line is None
        assert "layer=4" in t.to_line()

    def test_field_assignment_auto_dirties(self):
        t = Text(
            text="My Label",
            x=100,
            y=-400,
            rotation=0,
            mirror=0,
            xscale=0.3,
            yscale=0.3,
            raw_line="T {My Label} 100 -400 0 0 0.3 0.3 {}",
        )
        t.x = 150
        assert t.raw_line is None
        assert t.to_line() == "T {My Label} 150 -400 0 0 0.3 0.3 {}"


class TestGraphicLine:
    def test_to_line(self):
        gl = GraphicLine(layer=4, x1=0, y1=0, x2=100, y2=100)
        assert gl.to_line() == "L 4 0 0 100 100 {}"

    def test_raw_line_preserved(self):
        original = "L 4 0 0 100 100 {}"
        gl = GraphicLine(layer=4, x1=0, y1=0, x2=100, y2=100, raw_line=original)
        assert gl.to_line() == original

    def test_set_attribute_clears_raw_line(self):
        gl = GraphicLine(
            layer=4,
            x1=0,
            y1=0,
            x2=100,
            y2=100,
            raw_line="L 4 0 0 100 100 {}",
        )
        gl.set_attribute("dash", "4")
        assert gl.raw_line is None
        assert gl.to_line() == "L 4 0 0 100 100 {dash=4}"

    def test_field_assignment_auto_dirties(self):
        gl = GraphicLine(
            layer=4,
            x1=0,
            y1=0,
            x2=100,
            y2=100,
            raw_line="L 4 0 0 100 100 {}",
        )
        gl.x2 = 125
        assert gl.raw_line is None
        assert gl.to_line() == "L 4 0 0 125 100 {}"


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

    def test_set_attribute_clears_raw_line(self):
        b = Box(
            layer=4,
            x1=0,
            y1=0,
            x2=200,
            y2=100,
            raw_line="B 4 0 0 200 100 {}",
        )
        b.set_attribute("dash", "4")
        assert b.raw_line is None
        assert b.to_line() == "B 4 0 0 200 100 {dash=4}"

    def test_field_assignment_auto_dirties(self):
        b = Box(
            layer=4,
            x1=0,
            y1=0,
            x2=200,
            y2=100,
            raw_line="B 4 0 0 200 100 {}",
        )
        b.y2 = 125
        assert b.raw_line is None
        assert b.to_line() == "B 4 0 0 200 125 {}"


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

    def test_set_attribute_clears_raw_line(self):
        a = Arc(
            layer=4,
            x=100,
            y=100,
            r=50.0,
            start_angle=0.0,
            sweep_angle=360.0,
            raw_line="A 4 100 100 50 0 360 {}",
        )
        a.set_attribute("dash", "2")
        assert a.raw_line is None
        assert a.to_line() == "A 4 100 100 50 0 360 {dash=2}"

    def test_field_assignment_auto_dirties(self):
        a = Arc(
            layer=4,
            x=100,
            y=100,
            r=50.0,
            start_angle=0.0,
            sweep_angle=360.0,
            raw_line="A 4 100 100 50 0 360 {}",
        )
        a.r = 75
        assert a.raw_line is None
        assert a.to_line() == "A 4 100 100 75 0 360 {}"


class TestPolygon:
    def test_to_line(self):
        p = Polygon(layer=4, points=[(0, 0), (100, 0), (50, 100)])
        assert p.to_line() == "P 4 3 0 0 100 0 50 100 {}"

    def test_raw_line_preserved(self):
        original = "P 4 3 0 0 100 0 50 100 {}"
        p = Polygon(layer=4, points=[(0, 0), (100, 0), (50, 100)], raw_line=original)
        assert p.to_line() == original

    def test_set_attribute_clears_raw_line(self):
        p = Polygon(
            layer=4,
            points=[(0, 0), (100, 0), (50, 100)],
            raw_line="P 4 3 0 0 100 0 50 100 {}",
        )
        p.set_attribute("dash", "3")
        assert p.raw_line is None
        assert p.to_line() == "P 4 3 0 0 100 0 50 100 {dash=3}"

    def test_mark_dirty_needed_for_list_mutation(self):
        """In-place list mutation needs mark_dirty (no __setattr__)."""
        p = Polygon(
            layer=4,
            points=[(0, 0), (100, 0), (50, 100)],
            raw_line="P 4 3 0 0 100 0 50 100 {}",
        )
        p.points.append((25, 50))
        # raw_line is NOT auto-cleared for in-place list mutation
        assert p.raw_line is not None
        p.mark_dirty()
        assert p.to_line() == "P 4 4 0 0 100 0 50 100 25 50 {}"

    def test_field_reassignment_auto_dirties(self):
        """Full field reassignment (not in-place mutation) does auto-dirty."""
        p = Polygon(
            layer=4,
            points=[(0, 0), (100, 0), (50, 100)],
            raw_line="P 4 3 0 0 100 0 50 100 {}",
        )
        p.points = [(0, 0), (200, 0), (100, 200)]
        assert p.raw_line is None
        assert p.to_line() == "P 4 3 0 0 200 0 100 200 {}"


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

    def test_default_schematic(self):
        h = Header.default_schematic()
        assert h.to_lines() == [
            "v {xschem version=3.4.5 file_version=1.2}",
            "G {}",
            "K {}",
            "V {}",
            "S {}",
            "E {}",
        ]

    def test_default_symbol(self):
        h = Header.default_symbol()
        assert h.to_lines() == [
            "v {xschem version=3.4.5 file_version=1.2}",
            "G {}",
            "K {}",
            "V {}",
            "S {}",
            "F {}",
            "E {}",
        ]


class TestRawLine:
    def test_preserves_unknown_line(self):
        line = "Z some_future_type 1 2 3 {}"
        r = RawLine(line=line)
        assert r.to_line() == line
