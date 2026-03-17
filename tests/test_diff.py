"""Tests for schematic diffing."""

from pyxschem.diff import diff_schematics
from pyxschem.model import Text
from pyxschem.schematic import Schematic


def _make_pair():
    """Create two identical simple schematics."""
    old = Schematic.new()
    old.add_component("resistor.sym", 100, 200, attributes={"name": "R1", "value": "1k"})
    old.add_component("capacitor.sym", 300, 200, attributes={"name": "C1", "value": "10n"})
    old.add_net(100, 200, 300, 200)

    new = Schematic.new()
    new.add_component("resistor.sym", 100, 200, attributes={"name": "R1", "value": "1k"})
    new.add_component("capacitor.sym", 300, 200, attributes={"name": "C1", "value": "10n"})
    new.add_net(100, 200, 300, 200)

    return old, new


class TestDiffIdentical:
    def test_identical_schematics_produce_empty_diff(self):
        old, new = _make_pair()
        diff = diff_schematics(old, new)
        assert diff.is_empty

    def test_diff_method_on_schematic(self):
        old, new = _make_pair()
        diff = old.diff(new)
        assert diff.is_empty


class TestComponentChanges:
    def test_added_component(self):
        old, new = _make_pair()
        new.add_component("inductor.sym", 500, 200, attributes={"name": "L1"})
        diff = diff_schematics(old, new)
        assert len(diff.component_changes) == 1
        ch = diff.component_changes[0]
        assert ch.kind == "added"
        assert ch.name == "L1"
        assert ch.old is None
        assert ch.new is not None

    def test_removed_component(self):
        old, new = _make_pair()
        old.add_component("inductor.sym", 500, 200, attributes={"name": "L1"})
        diff = diff_schematics(old, new)
        assert len(diff.component_changes) == 1
        ch = diff.component_changes[0]
        assert ch.kind == "removed"
        assert ch.name == "L1"

    def test_modified_component_value(self):
        old, new = _make_pair()
        # Change R1's value in new
        r1 = new.get_component("R1")
        r1.set_attribute("value", "4.7k")
        diff = diff_schematics(old, new)
        assert len(diff.component_changes) == 1
        ch = diff.component_changes[0]
        assert ch.kind == "modified"
        assert ch.name == "R1"
        assert ch.changed_attrs == {"value": ("1k", "4.7k")}

    def test_modified_component_symbol(self):
        old = Schematic.new()
        old.add_component("resistor.sym", 100, 200, attributes={"name": "R1"})
        new = Schematic.new()
        new.add_component("res_hi_prec.sym", 100, 200, attributes={"name": "R1"})
        diff = diff_schematics(old, new)
        assert len(diff.component_changes) == 1
        ch = diff.component_changes[0]
        assert ch.kind == "modified"
        assert "symbol" in ch.changed_attrs

    def test_unnamed_components_keyed_by_position(self):
        old = Schematic.new()
        old.add_component("gnd.sym", 100, 300)
        new = Schematic.new()
        # Same symbol, different position → added + removed
        new.add_component("gnd.sym", 200, 300)
        diff = diff_schematics(old, new)
        assert len(diff.component_changes) == 2
        kinds = {ch.kind for ch in diff.component_changes}
        assert kinds == {"added", "removed"}

    def test_position_only_change_not_reported(self):
        old = Schematic.new()
        old.add_component("resistor.sym", 100, 200, attributes={"name": "R1", "value": "1k"})
        new = Schematic.new()
        new.add_component("resistor.sym", 999, 999, attributes={"name": "R1", "value": "1k"})
        diff = diff_schematics(old, new)
        assert diff.is_empty


class TestNetChanges:
    def test_added_net(self):
        old, new = _make_pair()
        new.add_net(300, 200, 500, 200)
        diff = diff_schematics(old, new)
        assert len(diff.net_changes) == 1
        assert diff.net_changes[0].kind == "added"

    def test_removed_net(self):
        old, new = _make_pair()
        old.add_net(300, 200, 500, 200)
        diff = diff_schematics(old, new)
        assert len(diff.net_changes) == 1
        assert diff.net_changes[0].kind == "removed"


class TestTextChanges:
    def test_added_text(self):
        old = Schematic.new()
        new = Schematic.new()
        new._elements.append(
            Text(text="hello", x=0, y=0, rotation=0, mirror=0, xscale=1, yscale=1)
        )
        diff = diff_schematics(old, new)
        assert len(diff.text_changes) == 1
        assert diff.text_changes[0].kind == "added"

    def test_removed_text(self):
        old = Schematic.new()
        old._elements.append(
            Text(text="hello", x=0, y=0, rotation=0, mirror=0, xscale=1, yscale=1)
        )
        new = Schematic.new()
        diff = diff_schematics(old, new)
        assert len(diff.text_changes) == 1
        assert diff.text_changes[0].kind == "removed"


class TestIsEmpty:
    def test_is_empty_true_for_empty_diff(self):
        diff = diff_schematics(Schematic.new(), Schematic.new())
        assert diff.is_empty

    def test_is_empty_false_with_changes(self):
        old = Schematic.new()
        new = Schematic.new()
        new.add_component("r.sym", 0, 0, attributes={"name": "R1"})
        diff = diff_schematics(old, new)
        assert not diff.is_empty
