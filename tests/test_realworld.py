"""Tests against real xschem .sch files from the xschem repository."""

from pathlib import Path

import pytest

from pyxschem import Schematic
from pyxschem.model import RawLine

REAL_FIXTURES = Path(__file__).parent / "fixtures" / "real"
REAL_FILES = sorted(REAL_FIXTURES.glob("*.sch"))


@pytest.fixture(params=REAL_FILES, ids=lambda p: p.name)
def sch_file(request):
    return request.param


class TestRealWorldParsing:
    def test_loads_without_error(self, sch_file):
        sch = Schematic.load(sch_file)
        assert sch.header is not None

    def test_round_trip_byte_identical(self, sch_file):
        original = sch_file.read_text()
        sch = Schematic.load(sch_file)
        assert sch.to_text() == original

    def test_no_rawline_fallbacks(self, sch_file):
        sch = Schematic.load(sch_file)
        raw_lines = [
            e for e in sch._elements if isinstance(e, RawLine) and e.line.strip()
        ]
        assert raw_lines == [], (
            f"Unexpected RawLine elements: {[r.line for r in raw_lines]}"
        )

    def test_components_have_names(self, sch_file):
        sch = Schematic.load(sch_file)
        for c in sch.components:
            assert c.name is not None, f"Component missing name: {c.to_line()[:80]}"


class TestSpecificFiles:
    def test_poweramp_component_count(self):
        sch = Schematic.load(REAL_FIXTURES / "poweramp.sch")
        assert len(sch.components) == 86
        assert len(sch.nets) == 67

    def test_cmos_inv_query(self):
        sch = Schematic.load(REAL_FIXTURES / "cmos_inv.sch")
        components = sch.get_components()
        assert len(components) > 0

    def test_rlc_has_components(self):
        sch = Schematic.load(REAL_FIXTURES / "rlc.sch")
        assert len(sch.components) == 14

    def test_nand2_nets(self):
        sch = Schematic.load(REAL_FIXTURES / "nand2.sch")
        assert len(sch.nets) == 20
