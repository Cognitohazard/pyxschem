"""Tests for the project-tree audit module."""

from collections import Counter
from pathlib import Path

import pytest

from pyxschem import (
    FileReport,
    ProjectReport,
    Schematic,
    SymbolLibrary,
    XschemConfig,
    audit_tree,
)

FIXTURES = Path(__file__).parent / "fixtures"
DEVICES = Path("/usr/share/xschem/xschem_library/devices")

pytestmark = pytest.mark.skipif(
    not (DEVICES / "res.sym").is_file(),
    reason="xschem device library not installed at /usr/share/xschem",
)


def _devices_libs() -> SymbolLibrary:
    return SymbolLibrary.from_config(XschemConfig.from_paths([DEVICES]))


@pytest.fixture
def broken_tree(tmp_path: Path) -> Path:
    """Synthesise a 4-file project: 1 unresolved symbol, 1 missing value,
    1 missing name, 1 clean."""
    sch_a = Schematic.new()
    sch_a.add_component("totally_made_up_xyz.sym", 100, -100,
                         attributes={"name": "X1"})
    sch_a.save(tmp_path / "a.sch")

    sch_b = Schematic.new()
    sch_b.add_component("res.sym", 100, -100, attributes={"name": "R1"})
    sch_b.save(tmp_path / "b.sch")

    sch_c = Schematic.new()
    sch_c.add_component("res.sym", 100, -100, attributes={"value": "1k"})
    sch_c.save(tmp_path / "c.sch")

    sch_d = Schematic.new()
    sch_d.add_component("res.sym", 100, -100,
                         attributes={"name": "R1", "value": "10k"})
    sch_d.save(tmp_path / "d.sch")
    return tmp_path


class TestAuditTree:
    def test_walks_tree_in_sorted_order(self, broken_tree: Path):
        rep = audit_tree(broken_tree, _devices_libs())
        assert isinstance(rep, ProjectReport)
        assert rep.n_files == 4
        names = [f.path.name for f in rep.files]
        assert names == sorted(names)

    def test_each_file_report_is_a_FileReport(self, broken_tree: Path):
        rep = audit_tree(broken_tree, _devices_libs())
        assert all(isinstance(f, FileReport) for f in rep.files)

    def test_unresolved_symbol_flagged(self, broken_tree: Path):
        rep = audit_tree(broken_tree, _devices_libs())
        a = next(f for f in rep.files if f.path.name == "a.sch")
        assert a.unresolved_symbols == Counter({"totally_made_up_xyz.sym": 1})
        assert not a.is_clean

    def test_missing_value_flagged(self, broken_tree: Path):
        rep = audit_tree(broken_tree, _devices_libs())
        b = next(f for f in rep.files if f.path.name == "b.sch")
        assert b.missing_value == ["R1"]
        assert not b.is_clean

    def test_missing_name_flagged(self, broken_tree: Path):
        rep = audit_tree(broken_tree, _devices_libs())
        c = next(f for f in rep.files if f.path.name == "c.sch")
        assert c.missing_name == ["res.sym"]
        assert not c.is_clean

    def test_clean_file_is_clean(self, broken_tree: Path):
        rep = audit_tree(broken_tree, _devices_libs())
        d = next(f for f in rep.files if f.path.name == "d.sch")
        assert d.is_clean

    def test_pattern_filter(self, broken_tree: Path, tmp_path: Path):
        # Drop a non-matching file; the audit should ignore it.
        (broken_tree / "ignore.txt").write_text("nothing")
        rep = audit_tree(broken_tree, _devices_libs(), pattern="*.sch")
        assert all(f.path.suffix == ".sch" for f in rep.files)

    def test_value_prefixes_override(self, tmp_path: Path):
        sch = Schematic.new()
        # X1 normally is not a "needs value" prefix; opt in.
        sch.add_component("res.sym", 100, -100, attributes={"name": "X1"})
        sch.save(tmp_path / "x.sch")
        rep = audit_tree(tmp_path, _devices_libs(),
                          value_prefixes={"X"})
        x = next(f for f in rep.files if f.path.name == "x.sch")
        assert x.missing_value == ["X1"]

    def test_skip_validation_zeroes_validation_counts(self, broken_tree: Path):
        rep = audit_tree(broken_tree, _devices_libs(), skip_validation=True)
        assert all(f.validation_errors == 0 for f in rep.files)
        assert all(f.validation_warnings == 0 for f in rep.files)

    def test_unresolved_counted_once_per_instance(self, tmp_path: Path):
        sch = Schematic.new()
        for i in range(3):
            sch.add_component("missing_sym.sym", 100 * i, -100,
                               attributes={"name": f"X{i+1}"})
        sch.save(tmp_path / "multi.sch")
        rep = audit_tree(tmp_path, _devices_libs())
        f = rep.files[0]
        assert f.unresolved_symbols == Counter({"missing_sym.sym": 3})
        assert sum(f.unresolved_symbols.values()) == 3


class TestProjectReport:
    def test_totals(self, broken_tree: Path):
        rep = audit_tree(broken_tree, _devices_libs())
        assert rep.total_unresolved == 1
        assert rep.total_missing_value == 1
        assert rep.total_missing_name == 1

    def test_unresolved_by_symbol(self, broken_tree: Path):
        rep = audit_tree(broken_tree, _devices_libs())
        grouped = rep.unresolved_by_symbol()
        assert grouped == {
            "totally_made_up_xyz.sym": [broken_tree / "a.sch"],
        }

    def test_unresolved_by_symbol_groups_across_files(self, tmp_path: Path):
        for name in ("one.sch", "two.sch"):
            sch = Schematic.new()
            sch.add_component("missing.sym", 0, 0, attributes={"name": "X1"})
            sch.save(tmp_path / name)
        rep = audit_tree(tmp_path, _devices_libs())
        grouped = rep.unresolved_by_symbol()
        assert sorted(p.name for p in grouped["missing.sym"]) == ["one.sch", "two.sch"]

    def test_summary_renders_per_file_markers(self, broken_tree: Path):
        rep = audit_tree(broken_tree, _devices_libs())
        summary = rep.summary()
        # Three flagged + one clean → 3 [BAD] / 1 [OK]
        assert summary.count("[BAD]") == 3
        assert summary.count("[OK]") == 1
        assert "3/4 file(s) flagged" in summary

    def test_is_clean_when_no_problems(self, tmp_path: Path):
        sch = Schematic.new()
        sch.add_component("res.sym", 0, 0,
                           attributes={"name": "R1", "value": "1k"})
        sch.save(tmp_path / "ok.sch")
        rep = audit_tree(tmp_path, _devices_libs())
        assert rep.is_clean is True


class TestFileReport:
    def test_clean_default(self):
        rep = FileReport(path=Path("x.sch"))
        assert rep.is_clean is True

    def test_unresolved_symbols_is_counter(self):
        rep = FileReport(path=Path("x.sch"))
        assert isinstance(rep.unresolved_symbols, Counter)

    def test_dirty_when_any_field_populated(self):
        rep = FileReport(path=Path("x.sch"))
        rep.unresolved_symbols["foo.sym"] = 1
        assert rep.is_clean is False
