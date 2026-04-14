"""Tests for the Schematic high-level API."""

from pathlib import Path

import pytest
from conftest import make_symbol, mock_libs

from pyxschem import Component, Net, Schematic, Symbol, Text
from pyxschem.geometry import BBox, GeometryQuery

FIXTURES = Path(__file__).parent / "fixtures"


class TestLoadSave:
    def test_load_simple(self):
        sch = Schematic.load(FIXTURES / "simple.sch")
        assert len(sch.components) == 3
        assert len(sch.nets) == 3
        assert len(sch.texts) == 1
        assert sch.header is not None

    def test_save_round_trip(self, tmp_path):
        original = (FIXTURES / "simple.sch").read_text()
        sch = Schematic.load(FIXTURES / "simple.sch")
        out = tmp_path / "output.sch"
        sch.save(out)
        assert out.read_text() == original

    def test_from_text(self):
        text = (FIXTURES / "simple.sch").read_text()
        sch = Schematic.from_text(text)
        assert len(sch.components) == 3

    def test_new_empty(self):
        sch = Schematic.new()
        assert sch.components == []
        assert sch.nets == []
        assert sch.header is not None
        assert sch.version == "3.4.5"

    def test_to_text(self):
        text = (FIXTURES / "simple.sch").read_text()
        sch = Schematic.from_text(text)
        assert sch.to_text() == text

    def test_save_without_path_uses_original(self, tmp_path):
        src = tmp_path / "test.sch"
        src.write_text((FIXTURES / "simple.sch").read_text())
        sch = Schematic.load(src)
        sch.set_component_value("R1", "4.7k")
        sch.save()
        reloaded = Schematic.load(src)
        assert reloaded.get_component("R1").value == "4.7k"

    def test_save_no_path_on_new_raises(self):
        sch = Schematic.new()
        with pytest.raises(ValueError, match="No path"):
            sch.save()


class TestQuery:
    def test_get_component_by_name(self):
        sch = Schematic.load(FIXTURES / "simple.sch")
        r1 = sch.get_component("R1")
        assert r1 is not None
        assert r1.symbol == "devices/res.sym"
        assert r1.value == "10k"

    def test_get_component_not_found(self):
        sch = Schematic.load(FIXTURES / "simple.sch")
        assert sch.get_component("NONEXIST") is None

    def test_get_components_by_prefix(self):
        sch = Schematic.load(FIXTURES / "simple.sch")
        resistors = sch.get_components(prefix="R")
        assert len(resistors) == 1
        assert resistors[0].name == "R1"

    def test_get_components_by_symbol(self):
        sch = Schematic.load(FIXTURES / "simple.sch")
        res = sch.get_components(symbol="devices/res.sym")
        assert len(res) == 1

    def test_get_components_no_filter(self):
        sch = Schematic.load(FIXTURES / "simple.sch")
        assert len(sch.get_components()) == 3

    def test_get_nets_by_label(self):
        sch = Schematic.load(FIXTURES / "simple.sch")
        vdd_nets = sch.get_nets(label="VDD")
        assert len(vdd_nets) == 1

    def test_get_nets_all(self):
        sch = Schematic.load(FIXTURES / "simple.sch")
        assert len(sch.get_nets()) == 3


class TestMutation:
    def test_set_component_value(self):
        sch = Schematic.load(FIXTURES / "simple.sch")
        sch.set_component_value("R1", "4.7k")
        r1 = sch.get_component("R1")
        assert r1.value == "4.7k"
        assert r1.raw_line is None  # dirty

    def test_set_component_attribute(self):
        sch = Schematic.load(FIXTURES / "simple.sch")
        sch.set_component_attribute("R1", "m", "2")
        r1 = sch.get_component("R1")
        assert r1.attributes["m"] == "2"

    def test_set_value_missing_raises(self):
        sch = Schematic.load(FIXTURES / "simple.sch")
        with pytest.raises(ValueError, match="not found"):
            sch.set_component_value("NOPE", "1k")

    def test_set_attribute_missing_raises(self):
        sch = Schematic.load(FIXTURES / "simple.sch")
        with pytest.raises(ValueError, match="not found"):
            sch.set_component_attribute("NOPE", "m", "1")

    def test_remove_component(self):
        sch = Schematic.load(FIXTURES / "simple.sch")
        assert len(sch.components) == 3
        sch.remove_component("R1")
        assert len(sch.components) == 2
        assert sch.get_component("R1") is None

    def test_remove_missing_raises(self):
        sch = Schematic.load(FIXTURES / "simple.sch")
        with pytest.raises(ValueError, match="not found"):
            sch.remove_component("NOPE")

    def test_add_component(self):
        sch = Schematic.load(FIXTURES / "simple.sch")
        comp = sch.add_component(
            "devices/cap.sym",
            x=400,
            y=-200,
            attributes={"name": "C1", "value": "100n"},
        )
        assert isinstance(comp, Component)
        assert len(sch.components) == 4
        assert sch.get_component("C1") is not None
        assert sch.get_component("C1").value == "100n"

    def test_set_version_updates_header(self):
        sch = Schematic.load(FIXTURES / "simple.sch")
        sch.set_version("9.9.9", "2.0")
        assert sch.version == "9.9.9"
        assert sch.header.raw_lines[0] == "v {xschem version=9.9.9 file_version=2.0}"

    def test_set_version_creates_header_when_missing(self):
        sch = Schematic.from_text("N 0 0 100 0 {}\n")
        assert sch.header is None
        sch.set_version("9.9.9", "2.0")
        assert sch.header is not None
        assert sch.header.raw_lines[0] == "v {xschem version=9.9.9 file_version=2.0}"

    def test_add_text(self):
        sch = Schematic.new()
        text = sch.add_text("hello", 10, 20)
        assert text in sch.texts
        assert "T {hello} 10 20 0 0 0.4 0.4 {}" in sch.to_text()

    def test_add_graphics_and_accessors(self):
        sch = Schematic.new()
        line = sch.add_line(4, 0, 0, 10, 10)
        box = sch.add_box(4, 0, 0, 20, 10)
        arc = sch.add_arc(4, 10, 10, 5, 0, 180)
        polygon = sch.add_polygon(4, [(0, 0), (10, 0), (5, 5)])

        assert line in sch.lines
        assert box in sch.boxes
        assert arc in sch.arcs
        assert polygon in sch.polygons

    def test_remove_net_by_identity(self):
        sch = Schematic.load(FIXTURES / "simple.sch")
        net = sch.nets[0]
        sch.remove_net(net)
        assert net not in sch.nets

    def test_remove_text_by_identity(self):
        sch = Schematic.load(FIXTURES / "simple.sch")
        text = sch.texts[0]
        sch.remove_text(text)
        assert text not in sch.texts


class TestMutationRoundTrip:
    def test_modify_value_only_changes_that_line(self):
        sch = Schematic.load(FIXTURES / "simple.sch")
        sch.set_component_value("R1", "4.7k")
        text = sch.to_text()
        # R1 line should have new value
        assert "4.7k" in text
        # Other components should be unchanged (raw_line preserved)
        assert "C {devices/vsource.sym} 160 -130 0 0 {name=V1 value=1.8}" in text

    def test_add_component_appears_in_output(self):
        sch = Schematic.load(FIXTURES / "simple.sch")
        sch.add_component(
            "devices/cap.sym",
            x=400,
            y=-200,
            attributes={"name": "C1", "value": "100n"},
        )
        text = sch.to_text()
        assert "C {devices/cap.sym} 400 -200 0 0 {name=C1 value=100n}" in text

    def test_remove_component_gone_from_output(self):
        sch = Schematic.load(FIXTURES / "simple.sch")
        sch.remove_component("R1")
        text = sch.to_text()
        assert "R1" not in text
        assert "devices/res.sym" not in text

    def test_save_after_mutation(self, tmp_path):
        sch = Schematic.load(FIXTURES / "simple.sch")
        sch.set_component_value("R1", "4.7k")
        out = tmp_path / "modified.sch"
        sch.save(out)
        reloaded = Schematic.load(out)
        assert reloaded.get_component("R1").value == "4.7k"
        # Other values preserved
        assert reloaded.get_component("V1").value == "1.8"

    def test_field_assignment_auto_dirties_on_serialize(self):
        sch = Schematic.load(FIXTURES / "simple.sch")
        line = sch.lines[0]
        line.x1 = 75
        # No mark_dirty() needed — auto-dirty via __setattr__
        text = sch.to_text()
        assert "L 4 75 -350 400 -350 {}" in text

    def test_remove_net_error_guard(self):
        sch = Schematic.new()
        fake_net = Net(x1=0, y1=0, x2=1, y2=1)
        with pytest.raises(ValueError, match="Net not found"):
            sch.remove_net(fake_net)

    def test_remove_text_error_guard(self):
        sch = Schematic.new()
        fake_text = Text(
            text="x", x=0, y=0, rotation=0, mirror=0, xscale=0.4, yscale=0.4
        )
        with pytest.raises(ValueError, match="Text not found"):
            sch.remove_text(fake_text)


class TestGeometryQuery:
    def test_component_bbox_basic(self):
        sym = make_symbol(-10, -20, 10, 20)
        libs = mock_libs(("test.sym", sym))
        sch = Schematic.new()
        sch.add_component("test.sym", x=100, y=200, attributes={"name": "U1"})
        gq = GeometryQuery(sch, libs)
        assert gq.component_bbox("U1") == BBox(90, 180, 110, 220)

    def test_component_bbox_rotated_90(self):
        sym = make_symbol(0, 0, 10, 20)
        libs = mock_libs(("test.sym", sym))
        sch = Schematic.new()
        sch.add_component("test.sym", x=0, y=0, rotation=1, attributes={"name": "U1"})
        gq = GeometryQuery(sch, libs)
        assert gq.component_bbox("U1") == BBox(-20, 0, 0, 10)

    def test_component_bbox_mirrored(self):
        sym = make_symbol(0, 0, 10, 20)
        libs = mock_libs(("test.sym", sym))
        sch = Schematic.new()
        sch.add_component("test.sym", x=0, y=0, mirror=1, attributes={"name": "U1"})
        gq = GeometryQuery(sch, libs)
        assert gq.component_bbox("U1") == BBox(-10, 0, 0, 20)

    def test_component_bbox_not_found_raises(self):
        libs = mock_libs()
        sch = Schematic.new()
        gq = GeometryQuery(sch, libs)
        with pytest.raises(ValueError, match="not found"):
            gq.component_bbox("X1")

    def test_component_bbox_unresolvable_returns_none(self):
        libs = mock_libs()
        sch = Schematic.new()
        sch.add_component("unknown.sym", x=0, y=0, attributes={"name": "U1"})
        gq = GeometryQuery(sch, libs)
        assert gq.component_bbox("U1") is None

    def test_component_bbox_no_graphics_returns_none(self):
        sym = Symbol.new()  # no graphic elements
        libs = mock_libs(("test.sym", sym))
        sch = Schematic.new()
        sch.add_component("test.sym", x=0, y=0, attributes={"name": "U1"})
        gq = GeometryQuery(sch, libs)
        assert gq.component_bbox("U1") is None

    def test_component_bboxes_returns_all_named(self):
        sym = make_symbol(0, 0, 10, 10)
        libs = mock_libs(("test.sym", sym))
        sch = Schematic.new()
        sch.add_component("test.sym", x=0, y=0, attributes={"name": "U1"})
        sch.add_component("test.sym", x=100, y=0, attributes={"name": "U2"})
        gq = GeometryQuery(sch, libs)
        result = gq.component_bboxes()
        assert "U1" in result
        assert "U2" in result
        assert len(result) == 2

    def test_component_bboxes_skips_unnamed(self):
        sym = make_symbol(0, 0, 10, 10)
        libs = mock_libs(("test.sym", sym))
        sch = Schematic.new()
        sch.add_component("test.sym", x=0, y=0)  # no name
        gq = GeometryQuery(sch, libs)
        assert len(gq.component_bboxes()) == 0

    def test_component_bboxes_skips_unresolvable(self):
        libs = mock_libs()
        sch = Schematic.new()
        sch.add_component("unknown.sym", x=0, y=0, attributes={"name": "U1"})
        gq = GeometryQuery(sch, libs)
        assert len(gq.component_bboxes()) == 0

    def test_schematic_bbox_empty(self):
        libs = mock_libs()
        sch = Schematic.new()
        gq = GeometryQuery(sch, libs)
        assert gq.schematic_bbox() is None

    def test_schematic_bbox_nets_only(self):
        libs = mock_libs()
        sch = Schematic.new()
        sch.add_net(0, 0, 100, 0)
        sch.add_net(50, -50, 50, 50)
        gq = GeometryQuery(sch, libs)
        bb = gq.schematic_bbox()
        assert bb is not None
        assert bb.x1 == 0
        assert bb.y1 == -50
        assert bb.x2 == 100
        assert bb.y2 == 50

    def test_schematic_bbox_with_components(self):
        sym = make_symbol(-5, -5, 5, 5)
        libs = mock_libs(("test.sym", sym))
        sch = Schematic.new()
        sch.add_component("test.sym", x=50, y=50, attributes={"name": "U1"})
        gq = GeometryQuery(sch, libs)
        bb = gq.schematic_bbox()
        assert bb is not None
        assert bb.x1 <= 45
        assert bb.y1 <= 45
        assert bb.x2 >= 55
        assert bb.y2 >= 55

    def test_overlapping_components(self):
        sym = make_symbol(-10, -10, 10, 10)
        libs = mock_libs(("test.sym", sym))
        sch = Schematic.new()
        sch.add_component("test.sym", x=0, y=0, attributes={"name": "U1"})
        sch.add_component("test.sym", x=5, y=0, attributes={"name": "U2"})
        gq = GeometryQuery(sch, libs)
        overlaps = gq.overlapping_components()
        assert len(overlaps) == 1
        assert ("U1", "U2") in overlaps

    def test_pin_positions(self):

        sym = make_symbol(-10, -10, 10, 10)
        sym.add_pin("A", "in", 0, 0)
        libs = mock_libs(("test.sym", sym))
        sch = Schematic.new()
        sch.add_component("test.sym", x=50, y=50, attributes={"name": "U1"})
        gq = GeometryQuery(sch, libs)
        pins = gq.pin_positions()
        assert len(pins) == 1
        assert pins[0] == (50.0, 50.0, "U1", "A")
