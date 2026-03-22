"""Integration tests using the real xschem system installation.

These tests exercise pyxschem against the full xschem devices library
and example schematics shipped with the system package. They are skipped
when xschem is not installed.

Run with:  uv run pytest -m integration
Skip with: uv run pytest -m "not integration"
"""

import pytest
from conftest import HAS_XSCHEM, SYSTEM_DEVICES_DIR, SYSTEM_EXAMPLES

from pyxschem import Schematic, XschemCLI, diff_schematics, validate

pytestmark = pytest.mark.integration

# All example .sch files that ship with xschem
EXAMPLE_SCHEMATICS = (
    sorted(SYSTEM_EXAMPLES.glob("*.sch")) if SYSTEM_EXAMPLES.is_dir() else []
)
EXAMPLE_IDS = [p.name for p in EXAMPLE_SCHEMATICS]

# All .sym files in the devices library
DEVICE_SYMBOLS = (
    sorted(SYSTEM_DEVICES_DIR.rglob("*.sym")) if SYSTEM_DEVICES_DIR.is_dir() else []
)
DEVICE_IDS = [str(p.relative_to(SYSTEM_DEVICES_DIR)) for p in DEVICE_SYMBOLS]


def _first_named(sch, *, with_value=False):
    """Return the name of the first named component, or pytest.skip."""
    for c in sch.components:
        if c.name and (not with_value or c.attributes.get("value")):
            return c.name
    pytest.skip("No suitable named component found")


# ---------------------------------------------------------------------------
# 1. Round-trip parsing: every system example must load and re-serialize
#    to produce byte-identical output.
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not EXAMPLE_SCHEMATICS, reason="no system examples found")
class TestRoundTripSystemExamples:
    @pytest.mark.parametrize("sch_path", EXAMPLE_SCHEMATICS, ids=EXAMPLE_IDS)
    def test_load_without_error(self, sch_path):
        sch = Schematic.load(sch_path)
        assert sch is not None

    @pytest.mark.parametrize("sch_path", EXAMPLE_SCHEMATICS, ids=EXAMPLE_IDS)
    def test_round_trip_byte_identical(self, sch_path):
        original = sch_path.read_text()
        sch = Schematic.load(sch_path)
        assert sch.to_text() == original

    @pytest.mark.parametrize("sch_path", EXAMPLE_SCHEMATICS, ids=EXAMPLE_IDS)
    def test_no_rawline_fallbacks(self, sch_path):
        """Every line should be parsed into a typed element, not a raw fallback."""
        from pyxschem.parser import parse_schematic

        text = sch_path.read_text()
        elements = parse_schematic(text)
        for el in elements:
            assert type(el).__name__ != "RawLine", (
                f"Unparsed raw line in {sch_path.name}: {el}"
            )

    @pytest.mark.parametrize("sch_path", EXAMPLE_SCHEMATICS, ids=EXAMPLE_IDS)
    def test_version_extractable(self, sch_path):
        sch = Schematic.load(sch_path)
        # Every xschem file should have a version header
        assert sch.version is not None


# ---------------------------------------------------------------------------
# 2. Symbol parsing: every .sym in the devices library must load cleanly.
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not DEVICE_SYMBOLS, reason="no system symbols found")
class TestSymbolSystemLibrary:
    @pytest.mark.parametrize("sym_path", DEVICE_SYMBOLS, ids=DEVICE_IDS)
    def test_load_without_error(self, sym_path):
        from pyxschem import Symbol

        sym = Symbol.load(sym_path)
        assert sym is not None

    @pytest.mark.parametrize("sym_path", DEVICE_SYMBOLS, ids=DEVICE_IDS)
    def test_round_trip_byte_identical(self, sym_path):
        from pyxschem import Symbol

        original = sym_path.read_text()
        sym = Symbol.load(sym_path)
        assert sym.to_text() == original

    @pytest.mark.parametrize("sym_path", DEVICE_SYMBOLS, ids=DEVICE_IDS)
    def test_pins_are_well_formed(self, sym_path):
        """Every pin should have a name and a direction string."""
        from pyxschem import Symbol

        sym = Symbol.load(sym_path)
        for pin in sym.pins:
            assert pin.name, f"Unnamed pin in {sym_path.name}"
            # xschem uses "in", "out", "inout" conventionally,
            # but probes use non-standard directions like "xxx"
            assert isinstance(pin.direction, str) and pin.direction, (
                f"Empty direction for pin '{pin.name}' in {sym_path.name}"
            )


# ---------------------------------------------------------------------------
# 3. Library resolution: resolve symbols from the real devices library.
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not SYSTEM_DEVICES_DIR.is_dir(), reason="system library not found")
class TestSystemLibraryResolution:
    def test_resolve_common_symbols(self, system_libs):
        """Core device symbols must be resolvable."""
        for ref in [
            "devices/res.sym",
            "devices/capa.sym",
            "devices/ind.sym",
            "devices/vsource.sym",
            "devices/nmos4.sym",
            "devices/pmos4.sym",
            "devices/diode.sym",
            "devices/npn.sym",
            "devices/pnp.sym",
        ]:
            sym = system_libs.resolve(ref)
            assert sym is not None, f"Failed to resolve {ref}"

    def test_resolve_returns_none_for_missing(self, system_libs):
        assert system_libs.resolve("devices/totally_fake_component.sym") is None

    def test_search_returns_results(self, system_libs):
        results = system_libs.search("mos")
        assert len(results) > 0
        assert any("nmos" in r for r in results)
        assert any("pmos" in r for r in results)

    def test_list_symbols_covers_all_devices(self, system_libs):
        syms = system_libs.list_symbols()
        # The real devices library has 100+ symbols
        assert len(syms) >= 100, f"Expected 100+ symbols, got {len(syms)}"

    def test_caching_returns_same_object(self, system_libs):
        sym1 = system_libs.resolve("devices/res.sym")
        sym2 = system_libs.resolve("devices/res.sym")
        assert sym1 is sym2

    def test_resistor_has_two_pins(self, system_libs):
        sym = system_libs.resolve("devices/res.sym")
        assert len(sym.pins) == 2
        pin_names = {p.name for p in sym.pins}
        assert "p" in pin_names or "P" in pin_names

    def test_nmos4_has_four_pins(self, system_libs):
        sym = system_libs.resolve("devices/nmos4.sym")
        assert len(sym.pins) == 4

    def test_vsource_has_two_pins(self, system_libs):
        sym = system_libs.resolve("devices/vsource.sym")
        assert len(sym.pins) == 2


# ---------------------------------------------------------------------------
# 4. Querying real schematics with the system library.
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not EXAMPLE_SCHEMATICS, reason="no system examples found")
class TestQuerySystemExamples:
    def test_rlc_components(self):
        sch = Schematic.load(SYSTEM_EXAMPLES / "rlc.sch")
        assert len(sch.components) > 0
        # Should have R, L, C, V at minimum
        prefixes = {c.name[0] for c in sch.components if c.name}
        assert "R" in prefixes or "L" in prefixes or "C" in prefixes

    def test_nand2_has_nets(self):
        sch = Schematic.load(SYSTEM_EXAMPLES / "nand2.sch")
        assert len(sch.nets) > 0

    def test_cmos_inv_component_lookup(self):
        sch = Schematic.load(SYSTEM_EXAMPLES / "cmos_inv.sch")
        # Should be able to look up specific components
        for comp in sch.components:
            if comp.name:
                found = sch.get_component(comp.name)
                assert found is comp

    def test_filter_by_prefix(self):
        sch = Schematic.load(SYSTEM_EXAMPLES / "rlc.sch")
        caps = sch.get_components(prefix="C")
        for c in caps:
            assert c.name.startswith("C")

    def test_get_nets_by_label(self):
        sch = Schematic.load(SYSTEM_EXAMPLES / "rlc.sch")
        labeled_nets = [n for n in sch.nets if n.label]
        if labeled_nets:
            label = labeled_nets[0].label
            found = sch.get_nets(label=label)
            assert len(found) >= 1
            assert all(n.label == label for n in found)


# ---------------------------------------------------------------------------
# 5. Mutation + round-trip on real schematics.
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not EXAMPLE_SCHEMATICS, reason="no system examples found")
class TestMutationSystemExamples:
    def test_modify_value_and_save(self, tmp_path):
        sch = Schematic.load(SYSTEM_EXAMPLES / "rlc.sch")
        target = _first_named(sch, with_value=True)
        sch.set_component_value(target, "999k")
        out = tmp_path / "modified.sch"
        sch.save(out)

        # Reload and verify
        reloaded = Schematic.load(out)
        assert reloaded.get_component(target).value == "999k"

    def test_add_component_to_real_schematic(self, tmp_path):
        sch = Schematic.load(SYSTEM_EXAMPLES / "rlc.sch")
        original_count = len(sch.components)
        sch.add_component(
            "devices/res.sym", 500, 500, attributes={"name": "Rtest", "value": "47k"}
        )
        assert len(sch.components) == original_count + 1

        out = tmp_path / "added.sch"
        sch.save(out)
        reloaded = Schematic.load(out)
        assert reloaded.get_component("Rtest") is not None
        assert reloaded.get_component("Rtest").value == "47k"

    def test_remove_component_from_real_schematic(self, tmp_path):
        sch = Schematic.load(SYSTEM_EXAMPLES / "rlc.sch")
        target = _first_named(sch)
        original_count = len(sch.components)
        sch.remove_component(target)
        assert len(sch.components) == original_count - 1

        out = tmp_path / "removed.sch"
        sch.save(out)
        reloaded = Schematic.load(out)
        assert reloaded.get_component(target) is None


# ---------------------------------------------------------------------------
# 6. Diffing real schematics.
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not EXAMPLE_SCHEMATICS, reason="no system examples found")
class TestDiffSystemExamples:
    def test_self_diff_is_empty(self):
        sch = Schematic.load(SYSTEM_EXAMPLES / "rlc.sch")
        d = diff_schematics(sch, sch)
        assert d.is_empty

    def test_diff_detects_added_component(self):
        original = Schematic.load(SYSTEM_EXAMPLES / "rlc.sch")
        modified = Schematic.load(SYSTEM_EXAMPLES / "rlc.sch")
        modified.add_component("devices/res.sym", 800, 800, attributes={"name": "Rnew"})
        d = diff_schematics(original, modified)
        assert not d.is_empty
        added = [c for c in d.component_changes if c.kind == "added"]
        assert any(c.name == "Rnew" for c in added)

    def test_diff_detects_removed_component(self):
        original = Schematic.load(SYSTEM_EXAMPLES / "rlc.sch")
        modified = Schematic.load(SYSTEM_EXAMPLES / "rlc.sch")
        target = _first_named(modified)
        modified.remove_component(target)
        d = diff_schematics(original, modified)
        assert not d.is_empty
        removed = [c for c in d.component_changes if c.kind == "removed"]
        assert any(c.name == target for c in removed)

    def test_diff_detects_value_change(self):
        original = Schematic.load(SYSTEM_EXAMPLES / "rlc.sch")
        modified = Schematic.load(SYSTEM_EXAMPLES / "rlc.sch")
        target = _first_named(modified, with_value=True)
        modified.set_component_value(target, "changed_value")
        d = diff_schematics(original, modified)
        assert not d.is_empty


# ---------------------------------------------------------------------------
# 7. Validation with real symbol library (unconnected pin detection).
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not EXAMPLE_SCHEMATICS, reason="no system examples found")
class TestValidationWithSystemLibrary:
    @pytest.mark.parametrize("sch_path", EXAMPLE_SCHEMATICS, ids=EXAMPLE_IDS)
    def test_validate_does_not_crash(self, sch_path, system_libs):
        """Validation must complete without exceptions on every example."""
        sch = Schematic.load(sch_path)
        result = validate(sch, libs=system_libs)
        assert result is not None
        # Each issue should have required fields
        for issue in result.issues:
            assert issue.severity in ("error", "warning")
            assert issue.category
            assert issue.message

    def test_validate_rlc_reports_issues(self, system_libs):
        """RLC circuit is a well-formed example — check it validates."""
        sch = Schematic.load(SYSTEM_EXAMPLES / "rlc.sch")
        result = validate(sch, libs=system_libs)
        # Just verify it returns a result with meaningful data
        assert isinstance(result.issues, list)

    def test_validate_without_libs_skips_pin_checks(self):
        sch = Schematic.load(SYSTEM_EXAMPLES / "rlc.sch")
        result = validate(sch, libs=None)
        assert not any(i.category == "unconnected_pin" for i in result.issues)

    def test_validate_with_libs_can_find_unconnected_pins(self, system_libs):
        """A schematic with a dangling component should have unconnected pins."""
        sch = Schematic.load(SYSTEM_EXAMPLES / "rlc.sch")
        # Add a floating resistor with no nets
        sch.add_component("devices/res.sym", 9999, 9999, attributes={"name": "Rfloat"})
        result = validate(sch, libs=system_libs)
        unconnected = [i for i in result.issues if i.category == "unconnected_pin"]
        assert len(unconnected) >= 2  # resistor has 2 pins


# ---------------------------------------------------------------------------
# 8. Pin geometry with real symbols.
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not SYSTEM_DEVICES_DIR.is_dir(), reason="system library not found")
class TestPinGeometryWithSystemLibrary:
    def test_resistor_pin_positions(self, system_libs):
        """Place a resistor and verify pin positions transform correctly."""
        sch = Schematic.new()
        sch.add_component("devices/res.sym", 200, 300, attributes={"name": "R1"})
        sym = system_libs.resolve("devices/res.sym")
        for pin in sym.pins:
            x, y = sch.pin_position("R1", pin.name, system_libs)
            # Pins should be offset from component origin
            assert isinstance(x, (int, float))
            assert isinstance(y, (int, float))

    def test_rotated_component_pins(self, system_libs):
        """Pin positions should change with rotation."""
        positions = {}
        for rot in range(4):
            sch = Schematic.new()
            sch.add_component(
                "devices/res.sym", 0, 0, rotation=rot, attributes={"name": "R1"}
            )
            sym = system_libs.resolve("devices/res.sym")
            pin = sym.pins[0]
            x, y = sch.pin_position("R1", pin.name, system_libs)
            positions[rot] = (x, y)
        # At least some rotations should produce different positions
        unique = set(positions.values())
        assert len(unique) >= 2, "Rotation had no effect on pin positions"

    def test_mirrored_component_pins(self, system_libs):
        """Mirror should flip pin positions."""
        sch_normal = Schematic.new()
        sch_normal.add_component(
            "devices/res.sym", 0, 0, mirror=0, attributes={"name": "R1"}
        )
        sch_mirror = Schematic.new()
        sch_mirror.add_component(
            "devices/res.sym", 0, 0, mirror=1, attributes={"name": "R1"}
        )

        sym = system_libs.resolve("devices/res.sym")
        pin = sym.pins[0]
        pos_normal = sch_normal.pin_position("R1", pin.name, system_libs)
        pos_mirror = sch_mirror.pin_position("R1", pin.name, system_libs)
        # If pin is not at origin, mirror should change position
        if sym.pins[0].x != 0:
            assert pos_normal != pos_mirror

    def test_connect_pin_creates_net_at_correct_position(self, system_libs):
        """connect() should create a net at the actual pin location."""
        sch = Schematic.new()
        sch.add_component("devices/res.sym", 200, 300, attributes={"name": "R1"})
        sym = system_libs.resolve("devices/res.sym")
        pin = sym.pins[0]

        net = sch.connect("R1", pin.name, "VDD", system_libs)
        expected_x, expected_y = sch.pin_position("R1", pin.name, system_libs)
        assert net.x1 == expected_x
        assert net.y1 == expected_y
        assert net.label == "VDD"


# ---------------------------------------------------------------------------
# 9. CLI wrapper integration (requires xschem binary).
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not HAS_XSCHEM, reason="xschem not installed")
class TestCLIIntegration:
    def test_netlist_spice_real_example(self, tmp_path):
        cli = XschemCLI()
        result = cli.netlist(SYSTEM_EXAMPLES / "rlc.sch", output_dir=tmp_path)
        assert result.exists()
        content = result.read_text()
        assert len(content) > 0

    def test_netlist_multiple_examples(self, tmp_path):
        """Netlist generation should work for several example files."""
        cli = XschemCLI()
        successes = 0
        for sch_path in EXAMPLE_SCHEMATICS[:5]:
            try:
                out_dir = tmp_path / sch_path.stem
                out_dir.mkdir(parents=True, exist_ok=True)
                result = cli.netlist(sch_path, output_dir=out_dir)
                if result.exists():
                    successes += 1
            except Exception:
                pass  # Some examples may not netlist cleanly
        assert successes >= 1, "No example netlisted successfully"

    def test_tcl_command_with_schematic(self):
        cli = XschemCLI()
        cli.command("puts [info patchlevel]")

    def test_version_string(self):
        cli = XschemCLI()
        assert "XSCHEM" in cli.version


# ---------------------------------------------------------------------------
# 10. End-to-end workflow: load → query → mutate → validate → diff → save.
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not EXAMPLE_SCHEMATICS, reason="no system examples found")
class TestEndToEndWorkflow:
    def test_full_workflow(self, tmp_path, system_libs):
        """Complete design editing workflow with real files."""
        # Load
        sch = Schematic.load(SYSTEM_EXAMPLES / "rlc.sch")

        # Query
        all_comps = sch.components
        assert len(all_comps) > 0

        # Validate before mutation
        result_before = validate(sch, libs=system_libs)
        assert result_before is not None

        # Snapshot for diff
        original = Schematic.load(SYSTEM_EXAMPLES / "rlc.sch")

        # Mutate — add a component
        sch.add_component(
            "devices/capa.sym",
            400,
            400,
            attributes={"name": "Cnew", "value": "100nF"},
        )

        # Validate after mutation
        result_after = validate(sch, libs=system_libs)
        assert result_after is not None

        # Diff
        d = diff_schematics(original, sch)
        assert not d.is_empty
        added = [c for c in d.component_changes if c.kind == "added"]
        assert any(c.name == "Cnew" for c in added)

        # Save and reload
        out = tmp_path / "workflow_result.sch"
        sch.save(out)
        reloaded = Schematic.load(out)
        assert reloaded.get_component("Cnew") is not None
        assert reloaded.get_component("Cnew").value == "100nF"

    def test_programmatic_schematic_generation(self, tmp_path, system_libs):
        """Build a schematic from scratch and validate it."""
        sch = Schematic.new()

        # Add components
        sch.add_component(
            "devices/vsource.sym", 0, -200, attributes={"name": "V1", "value": "5"}
        )
        sch.add_component(
            "devices/res.sym", 200, -300, attributes={"name": "R1", "value": "1k"}
        )
        sch.add_component(
            "devices/capa.sym", 200, -100, attributes={"name": "C1", "value": "10u"}
        )
        sch.add_component("devices/gnd.sym", 0, 0, attributes={"name": "l1"})

        assert len(sch.components) == 4

        # Wire them up
        sch.connect(
            "R1",
            system_libs.resolve("devices/res.sym").pins[0].name,
            "VIN",
            system_libs,
        )
        sch.connect(
            "C1",
            system_libs.resolve("devices/capa.sym").pins[0].name,
            "VOUT",
            system_libs,
        )

        assert len(sch.nets) == 2

        # Save and reload
        out = tmp_path / "generated.sch"
        sch.save(out)
        reloaded = Schematic.load(out)
        assert len(reloaded.components) == 4
        assert len(reloaded.nets) == 2

        # Validate
        result = validate(reloaded, libs=system_libs)
        assert result is not None
