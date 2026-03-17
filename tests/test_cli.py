"""Tests for xschem CLI wrapper."""

import shutil
from pathlib import Path

import pytest

from pyxschem import XschemCLI

FIXTURES = Path(__file__).parent / "fixtures"
HAS_XSCHEM = shutil.which("xschem") is not None

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
