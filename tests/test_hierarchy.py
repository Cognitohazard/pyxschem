"""Tests for hierarchy traversal."""

from pathlib import Path

from pyxschem import Schematic, SymbolLibrary

HIER_FIXTURES = Path(__file__).parent / "fixtures" / "hierarchy"


def _load():
    """Load the test hierarchy."""
    sch = Schematic.load(HIER_FIXTURES / "top.sch")
    libs = SymbolLibrary([HIER_FIXTURES])
    return sch, libs


class TestWalkHierarchy:
    def test_top_level_nodes(self):
        sch, libs = _load()
        nodes = sch.hierarchy(libs)
        assert len(nodes) == 3
        paths = [n.path for n in nodes]
        assert paths == ["R1", "X1", "C1"]

    def test_subcircuit_detected(self):
        sch, libs = _load()
        nodes = sch.hierarchy(libs)
        r1, x1, c1 = nodes
        assert not r1.is_subcircuit
        assert x1.is_subcircuit
        assert not c1.is_subcircuit

    def test_subcircuit_children(self):
        sch, libs = _load()
        x1 = sch.hierarchy(libs)[1]
        assert len(x1.children) == 2
        paths = [c.path for c in x1.children]
        assert paths == ["X1.M1", "X1.X2"]

    def test_nested_subcircuit(self):
        sch, libs = _load()
        x1 = sch.hierarchy(libs)[1]
        x2 = x1.children[1]
        assert x2.is_subcircuit
        assert len(x2.children) == 1
        assert x2.children[0].path == "X1.X2.M3"

    def test_leaf_has_no_children(self):
        sch, libs = _load()
        r1 = sch.hierarchy(libs)[0]
        assert r1.children == []

    def test_subcircuit_has_schematic(self):
        sch, libs = _load()
        x1 = sch.hierarchy(libs)[1]
        assert x1.schematic is not None
        assert len(x1.schematic.components) == 2

    def test_leaf_has_no_schematic(self):
        sch, libs = _load()
        r1 = sch.hierarchy(libs)[0]
        assert r1.schematic is None

    def test_node_has_component_ref(self):
        sch, libs = _load()
        r1 = sch.hierarchy(libs)[0]
        assert r1.component.name == "R1"
        assert r1.symbol_path == "resistor.sym"


class TestFindAll:
    def test_find_by_prefix(self):
        sch, libs = _load()
        mosfets = sch.find_all(libs, prefix="M")
        paths = [n.path for n in mosfets]
        assert "X1.M1" in paths
        assert "X1.X2.M3" in paths
        assert len(paths) == 2

    def test_find_by_symbol(self):
        sch, libs = _load()
        nmos = sch.find_all(libs, symbol="nmos")
        assert len(nmos) == 2

    def test_find_no_match(self):
        sch, libs = _load()
        result = sch.find_all(libs, prefix="Z")
        assert result == []

    def test_find_top_level_component(self):
        sch, libs = _load()
        resistors = sch.find_all(libs, prefix="R")
        assert len(resistors) == 1
        assert resistors[0].path == "R1"


class TestFlatten:
    def test_flatten_returns_all_leaves(self):
        sch, libs = _load()
        leaves = sch.flatten(libs)
        paths = [n.path for n in leaves]
        assert len(leaves) == 4
        assert "R1" in paths
        assert "C1" in paths
        assert "X1.M1" in paths
        assert "X1.X2.M3" in paths

    def test_flatten_excludes_subcircuits(self):
        sch, libs = _load()
        leaves = sch.flatten(libs)
        for leaf in leaves:
            assert not leaf.is_subcircuit


class TestMissingSubcircuit:
    def test_missing_sch_treated_as_leaf(self):
        """Component referencing nonexistent .sch is a leaf, not an error."""
        sch = Schematic.from_text(
            "v {xschem version=3.4.5 file_version=1.2}\n"
            "G {}\nK {}\nV {}\nS {}\nE {}\n"
            "C {nonexistent.sch} 0 0 0 0 {name=X99}\n"
        )
        libs = SymbolLibrary([HIER_FIXTURES])
        nodes = sch.hierarchy(libs)
        assert len(nodes) == 1
        assert not nodes[0].is_subcircuit  # treated as leaf

    def test_sym_reference_is_always_leaf(self):
        sch = Schematic.from_text(
            "v {xschem version=3.4.5 file_version=1.2}\n"
            "G {}\nK {}\nV {}\nS {}\nE {}\n"
            "C {resistor.sym} 0 0 0 0 {name=R1}\n"
        )
        libs = SymbolLibrary([HIER_FIXTURES])
        nodes = sch.hierarchy(libs)
        assert len(nodes) == 1
        assert not nodes[0].is_subcircuit
