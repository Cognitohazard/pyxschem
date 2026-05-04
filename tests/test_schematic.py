"""Tests for the Schematic high-level API."""

from pathlib import Path

import pytest
from conftest import make_symbol, mock_libs

from pyxschem import (
    BomEntry,
    Component,
    Net,
    Schematic,
    SubcircuitPort,
    Symbol,
    Text,
)
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


# ---------------------------------------------------------------------------
# K-block / subcircuit metadata
# ---------------------------------------------------------------------------

class TestSubcircuitMetadata:
    def test_k_attributes_default_empty(self):
        sch = Schematic.new()
        assert sch.k_attributes() == {}

    def test_set_subcircuit_metadata_writes_type_format_template(self):
        sch = Schematic.new()
        sch.set_subcircuit_metadata(
            format="@name @pinlist @symname",
            template="name=X1 m=1",
        )
        attrs = sch.k_attributes()
        assert attrs["type"] == "subcircuit"
        assert "@pinlist" in attrs["format"]
        assert "name=X1" in attrs["template"]

    def test_set_subcircuit_metadata_round_trips(self, tmp_path):
        sch = Schematic.new()
        sch.set_subcircuit_metadata(format="@name @pinlist @symname")
        out = tmp_path / "sub.sch"
        sch.save(out)
        again = Schematic.load(out)
        assert again.k_attributes()["type"] == "subcircuit"

    def test_set_subcircuit_metadata_preserves_existing_keys(self):
        sch = Schematic.new()
        sch.set_subcircuit_metadata(format="A")
        sch.set_subcircuit_metadata(template="B")
        attrs = sch.k_attributes()
        assert attrs["format"] == "A"
        assert attrs["template"] == "B"

    def test_set_subcircuit_metadata_extra_kwargs(self):
        sch = Schematic.new()
        sch.set_subcircuit_metadata(format="A", function0="1 ~")
        assert sch.k_attributes()["function0"] == "1 ~"


class TestSubcircuitPorts:
    def test_empty_when_no_ports(self):
        sch = Schematic.new()
        sch.add_component("res.sym", 0, 0, attributes={"name": "R1"})
        assert sch.subcircuit_ports() == []

    def test_basename_form(self):
        sch = Schematic.new()
        sch.add_component("ipin.sym", 100, -200,
                           attributes={"name": "p1", "lab": "IN"})
        sch.add_component("opin.sym", 500, -200,
                           attributes={"name": "p2", "lab": "OUT"})
        ports = sch.subcircuit_ports()
        assert [p.direction for p in ports] == ["in", "out"]
        assert [p.name for p in ports] == ["IN", "OUT"]

    def test_subpath_form(self):
        sch = Schematic.new()
        sch.add_component("devices/ipin.sym", 0, 0,
                           attributes={"name": "p1", "lab": "A"})
        sch.add_component("devices/opin.sym", 100, 0,
                           attributes={"name": "p2", "lab": "Z"})
        sch.add_component("devices/iopin.sym", 50, 0,
                           attributes={"name": "p3", "lab": "BIDIR"})
        ports = sch.subcircuit_ports()
        assert [p.direction for p in ports] == ["in", "out", "inout"]
        assert [p.name for p in ports] == ["A", "Z", "BIDIR"]

    def test_returns_subcircuitport_instances(self):
        sch = Schematic.new()
        sch.add_component("ipin.sym", 50, -50,
                           attributes={"name": "p1", "lab": "X"})
        port = sch.subcircuit_ports()[0]
        assert isinstance(port, SubcircuitPort)
        assert (port.x, port.y) == (50, -50)

    def test_skips_components_without_lab(self):
        sch = Schematic.new()
        sch.add_component("ipin.sym", 0, 0, attributes={"name": "p1"})
        assert sch.subcircuit_ports() == []

    def test_preserves_declaration_order(self):
        sch = Schematic.new()
        sch.add_component("opin.sym", 0, 0,
                           attributes={"name": "p1", "lab": "Z"})
        sch.add_component("ipin.sym", 0, 0,
                           attributes={"name": "p2", "lab": "A"})
        sch.add_component("ipin.sym", 0, 0,
                           attributes={"name": "p3", "lab": "B"})
        assert [p.name for p in sch.subcircuit_ports()] == ["Z", "A", "B"]


# ---------------------------------------------------------------------------
# Refactor primitives
# ---------------------------------------------------------------------------

def _make_two_resistors() -> Schematic:
    sch = Schematic.new()
    sch.add_component("res.sym", 100, -100,
                       attributes={"name": "R1", "value": "1k"})
    sch.add_component("res.sym", 200, -100,
                       attributes={"name": "R2", "value": "2k"})
    return sch


class TestSetComponentAttributes:
    def test_sets_multiple_keys(self):
        sch = _make_two_resistors()
        sch.set_component_attributes("R1", w="2u", l="0.18u", m="4")
        r1 = sch.get_component("R1")
        assert r1.attributes["w"] == "2u"
        assert r1.attributes["l"] == "0.18u"
        assert r1.attributes["m"] == "4"

    def test_unknown_component_raises(self):
        sch = _make_two_resistors()
        with pytest.raises(ValueError, match="not found"):
            sch.set_component_attributes("NOPE", x="1")

    def test_no_kwargs_is_noop(self):
        sch = _make_two_resistors()
        before = dict(sch.get_component("R1").attributes)
        sch.set_component_attributes("R1")
        assert dict(sch.get_component("R1").attributes) == before


class TestBulkUpdate:
    def test_predicate_filters(self):
        sch = _make_two_resistors()
        n = sch.bulk_update(
            lambda c: c.attributes.get("value") == "1k",
            lambda c: c.set_attribute("tol", "1%"),
        )
        assert n == 1
        assert sch.get_component("R1").attributes.get("tol") == "1%"
        assert "tol" not in sch.get_component("R2").attributes

    def test_counts_all_matches(self):
        sch = _make_two_resistors()
        n = sch.bulk_update(
            lambda c: c.symbol == "res.sym",
            lambda c: c.set_attribute("m", "1"),
        )
        assert n == 2


class TestTransformComponents:
    def test_attrs_writes_literal(self):
        sch = _make_two_resistors()
        n = sch.transform_components(symbol="res.sym",
                                      attrs={"footprint": "0805"})
        assert n == 2
        for r in (sch.get_component("R1"), sch.get_component("R2")):
            assert r.attributes["footprint"] == "0805"

    def test_attr_remap_only_remaps_known_values(self):
        sch = _make_two_resistors()
        # Both R1 and R2 should match by symbol; remap touches only "1k".
        n = sch.transform_components(
            symbol="res.sym",
            attr_remap={"value": {"1k": "1.1k"}},
        )
        assert n == 1
        assert sch.get_component("R1").attributes["value"] == "1.1k"
        assert sch.get_component("R2").attributes["value"] == "2k"

    def test_no_op_remap_returns_zero(self):
        sch = _make_two_resistors()
        n = sch.transform_components(
            symbol="res.sym",
            attr_remap={"value": {"NEVER": "ALSO_NEVER"}},
        )
        assert n == 0

    def test_idempotent_retry_is_zero(self):
        sch = _make_two_resistors()
        sch.transform_components(symbol="res.sym",
                                  attr_remap={"value": {"1k": "9k"}})
        n2 = sch.transform_components(symbol="res.sym",
                                       attr_remap={"value": {"1k": "9k"}})
        assert n2 == 0

    def test_prefix_filter(self):
        sch = _make_two_resistors()
        sch.add_component("capa.sym", 50, -50,
                           attributes={"name": "C1", "value": "1u"})
        n = sch.transform_components(prefix="R",
                                      attrs={"footprint": "0805"})
        assert n == 2
        assert "footprint" not in sch.get_component("C1").attributes

    def test_empty_attrs_and_remap_returns_zero(self):
        sch = _make_two_resistors()
        assert sch.transform_components(symbol="res.sym") == 0


# ---------------------------------------------------------------------------
# BOM
# ---------------------------------------------------------------------------

class TestBom:
    def test_groups_by_symbol_value_footprint(self):
        sch = Schematic.new()
        sch.add_component("res.sym", 0, 0,
                           attributes={"name": "R1", "value": "1k",
                                       "footprint": "0805"})
        sch.add_component("res.sym", 100, 0,
                           attributes={"name": "R2", "value": "1k",
                                       "footprint": "0805"})
        sch.add_component("res.sym", 200, 0,
                           attributes={"name": "R3", "value": "10k",
                                       "footprint": "0805"})
        bom = sch.bom()
        assert all(isinstance(e, BomEntry) for e in bom)
        by_value = {e.value: e.count for e in bom}
        assert by_value == {"1k": 2, "10k": 1}

    def test_skips_helper_symbols_by_default(self):
        sch = Schematic.new()
        sch.add_component("res.sym", 0, 0,
                           attributes={"name": "R1", "value": "1k"})
        sch.add_component("lab_pin.sym", 0, 0,
                           attributes={"name": "lp_1", "lab": "VDD"})
        sch.add_component("gnd.sym", 0, 0,
                           attributes={"name": "g1", "lab": "GND"})
        sch.add_component("title.sym", 0, 0,
                           attributes={"name": "t1"})
        bom = sch.bom()
        symbols = {e.symbol for e in bom}
        assert symbols == {"res.sym"}

    def test_ignore_symbols_override(self):
        sch = Schematic.new()
        sch.add_component("res.sym", 0, 0,
                           attributes={"name": "R1", "value": "1k"})
        sch.add_component("lab_pin.sym", 0, 0,
                           attributes={"name": "lp_1", "lab": "VDD"})
        # Override: don't skip anything.
        bom = sch.bom(ignore_symbols=set())
        symbols = {e.symbol for e in bom}
        assert "lab_pin.sym" in symbols

    def test_flatten_requires_libs(self):
        sch = Schematic.new()
        sch.add_component("res.sym", 0, 0,
                           attributes={"name": "R1", "value": "1k"})
        with pytest.raises(ValueError, match="flatten=True requires libs"):
            sch.bom(flatten=True)

    def test_sorted_output(self):
        sch = Schematic.new()
        sch.add_component("res.sym", 0, 0,
                           attributes={"name": "R1", "value": "1k"})
        sch.add_component("capa.sym", 0, 0,
                           attributes={"name": "C1", "value": "1u"})
        bom = sch.bom()
        assert [e.symbol for e in bom] == sorted(e.symbol for e in bom)


# ---------------------------------------------------------------------------
# add_net(between=...) form
# ---------------------------------------------------------------------------

class TestAddNetBetween:
    def test_resolves_pin_pair(self):
        sym = make_symbol(-10, -10, 10, 10)
        sym.add_pin("P", "in", 0, -10)
        libs = mock_libs(("res.sym", sym))
        sch = Schematic.new()
        sch.add_component("res.sym", 100, -100,
                           attributes={"name": "R1"})
        sch.add_component("res.sym", 300, -100,
                           attributes={"name": "R2"})
        net = sch.add_net(between=(("R1", "P"), ("R2", "P")), libs=libs)
        # Both pins at y = -110 (anchor y=-100 + pin local y=-10)
        assert net.y1 == net.y2 == -110

    def test_diagonal_rejected(self):
        sym = make_symbol(-10, -10, 10, 10)
        sym.add_pin("P", "in", 0, -10)
        libs = mock_libs(("res.sym", sym))
        sch = Schematic.new()
        sch.add_component("res.sym", 100, -100, attributes={"name": "R1"})
        sch.add_component("res.sym", 300, -300, attributes={"name": "R2"})
        with pytest.raises(ValueError, match="orthogonally aligned"):
            sch.add_net(between=(("R1", "P"), ("R2", "P")), libs=libs)

    def test_libs_required(self):
        sch = Schematic.new()
        with pytest.raises(ValueError, match="requires libs"):
            sch.add_net(between=(("R1", "P"), ("R2", "P")))

    def test_mixed_form_rejected(self):
        sym = make_symbol(-10, -10, 10, 10)
        sym.add_pin("P", "in", 0, 0)
        libs = mock_libs(("res.sym", sym))
        sch = Schematic.new()
        sch.add_component("res.sym", 0, 0, attributes={"name": "R1"})
        sch.add_component("res.sym", 100, 0, attributes={"name": "R2"})
        with pytest.raises(ValueError, match="either coordinates or between"):
            sch.add_net(0, 0, 1, 1,
                         between=(("R1", "P"), ("R2", "P")), libs=libs)

    def test_partial_coords_rejected(self):
        sch = Schematic.new()
        with pytest.raises(ValueError,
                            match="all four coordinates or between"):
            sch.add_net(0, 0)

    def test_legacy_coordinate_form_still_works(self):
        sch = Schematic.new()
        net = sch.add_net(0, 0, 100, 0, label="VDD")
        assert net.label == "VDD"


class TestAddWireDelegates:
    def test_add_wire_creates_horizontal_segment(self):
        sym = make_symbol(-10, -10, 10, 10)
        sym.add_pin("P", "in", 0, 0)
        libs = mock_libs(("res.sym", sym))
        sch = Schematic.new()
        sch.add_component("res.sym", 0, 0, attributes={"name": "R1"})
        sch.add_component("res.sym", 100, 0, attributes={"name": "R2"})
        net = sch.add_wire("R1", "P", "R2", "P", libs)
        assert net.y1 == net.y2 == 0
