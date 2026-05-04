"""Tests for xschem CLI wrapper."""

import shutil
from pathlib import Path

import pytest
from conftest import HAS_XSCHEM

from pyxschem import XschemCLI

FIXTURES = Path(__file__).parent / "fixtures"

pytestmark = pytest.mark.skipif(not HAS_XSCHEM, reason="xschem not installed")


class TestDetection:
    def test_auto_detect(self):
        cli = XschemCLI()
        assert cli.binary.exists()

    def test_version_contains_xschem(self):
        cli = XschemCLI()
        assert "XSCHEM" in cli.version

    def test_explicit_binary(self):
        path = shutil.which("xschem")
        cli = XschemCLI(binary=path)
        assert cli.binary == Path(path)

    def test_missing_binary_raises(self):
        with pytest.raises(FileNotFoundError, match="not found"):
            XschemCLI(binary="/nonexistent/xschem")


class TestNetlist:
    def test_netlist_spice(self, tmp_path):
        cli = XschemCLI()
        result = cli.netlist(FIXTURES / "real" / "nand2.sch", output_dir=tmp_path)
        assert result.exists(), f"Netlist not found at {result}"
        content = result.read_text()
        assert len(content) > 0

    def test_netlist_default_temp_dir(self):
        cli = XschemCLI()
        result = cli.netlist(FIXTURES / "real" / "nand2.sch")
        assert result.parent.exists()

    def test_netlist_custom_name(self, tmp_path):
        cli = XschemCLI()
        result = cli.netlist(
            FIXTURES / "real" / "nand2.sch",
            output_dir=tmp_path,
            output_name="custom.spice",
        )
        assert result.name == "custom.spice"

    def test_netlist_returns_path(self, tmp_path):
        cli = XschemCLI()
        result = cli.netlist(FIXTURES / "real" / "nand2.sch", output_dir=tmp_path)
        assert isinstance(result, Path)

    def test_netlist_invalid_format(self, tmp_path):
        cli = XschemCLI()
        with pytest.raises(ValueError, match="Unknown format"):
            cli.netlist(FIXTURES / "real" / "nand2.sch", format="invalid")


class TestCommand:
    def test_command_executes(self):
        cli = XschemCLI()
        # Just verify it doesn't raise
        cli.command("puts hello")

    def test_run_with_args(self):
        cli = XschemCLI()
        result = cli.run(["--version"])
        assert "XSCHEM" in result.stdout


class TestNetlistText:
    def test_returns_string(self, tmp_path):
        cli = XschemCLI()
        text = cli.netlist_text(FIXTURES / "real" / "nand2.sch",
                                 output_dir=tmp_path)
        assert isinstance(text, str)
        assert text  # non-empty

    def test_matches_path_read_text(self, tmp_path):
        cli = XschemCLI()
        path = cli.netlist(FIXTURES / "real" / "nand2.sch",
                            output_dir=tmp_path)
        text_via_helper = cli.netlist_text(
            FIXTURES / "real" / "nand2.sch", output_dir=tmp_path)
        assert text_via_helper == path.read_text(encoding="utf-8")


class TestEnvAndCwd:
    def test_env_overlay_respected_by_run(self, tmp_path):
        cli = XschemCLI()
        # XSCHEM_LIBRARY_PATH=/nonexistent shouldn't crash --version.
        result = cli.run(["--version"], env={"XSCHEM_LIBRARY_PATH": "/nonexistent"})
        assert "XSCHEM" in result.stdout

    def test_unresolvable_symbol_raises(self, tmp_path):
        cli = XschemCLI()
        sch_path = tmp_path / "broken.sch"
        sch_path.write_text(
            "v {xschem version=3.4.5 file_version=1.2}\n"
            "G {}\nK {}\nV {}\nS {}\nE {}\n"
            "C {does_not_exist_xyz_test.sym} 100 -100 0 0 {name=X1}\n"
        )
        with pytest.raises(RuntimeError, match="MISSING"):
            cli.netlist(sch_path, output_dir=tmp_path)


class TestSession:
    def test_session_runs_buffered_commands(self):
        cli = XschemCLI()
        with cli.session() as s:
            s.run_tcl("puts cmd_a")
            s.run_tcl("puts [expr 7 * 6]")
        assert "cmd_a" in s.stdout
        assert "42" in s.stdout

    def test_session_run_tcl_after_flush_raises(self):
        cli = XschemCLI()
        with cli.session() as s:
            s.run_tcl("puts x")
        with pytest.raises(RuntimeError, match="already flushed"):
            s.run_tcl("puts y")

    def test_empty_session_does_not_invoke_xschem(self):
        cli = XschemCLI()
        with cli.session() as s:
            pass
        # No commands queued → no stdout produced.
        assert s.stdout == ""

    def test_explicit_flush_is_idempotent(self):
        cli = XschemCLI()
        with cli.session() as s:
            s.run_tcl("puts hello")
            s.flush()
            stdout_first = s.stdout
            s.flush()
            assert s.stdout == stdout_first
