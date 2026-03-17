"""Tests for the Schematic high-level API."""

from pathlib import Path

import pytest

from pyxschem import Component, Schematic

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
        assert sch.header is None

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
            "devices/cap.sym", x=400, y=-200,
            attributes={"name": "C1", "value": "100n"},
        )
        assert isinstance(comp, Component)
        assert len(sch.components) == 4
        assert sch.get_component("C1") is not None
        assert sch.get_component("C1").value == "100n"


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
            "devices/cap.sym", x=400, y=-200,
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
