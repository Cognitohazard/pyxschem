"""Thin wrapper for the xschem binary.

Delegates netlisting and batch commands to xschem — does not
reimplement xschem behavior. Follows the spicelib pattern:
Editor (pyxschem) + SimRunner (xschem CLI).
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

_FORMAT_FLAGS = {
    "spice": "-s",
    "verilog": "-w",
    "vhdl": "-V",
}


class XschemCLI:
    """Wrapper for the xschem command-line tool.

    Usage::

        cli = XschemCLI()  # auto-detect binary
        netlist_path = cli.netlist("amplifier.sch", output_dir="build/")
        cli.command("puts [xschem get instances]")
    """

    def __init__(self, binary: str | Path | None = None) -> None:
        if binary is not None:
            self._binary = Path(binary)
            if not self._binary.exists():
                raise FileNotFoundError(f"xschem binary not found: {self._binary}")
        else:
            found = shutil.which("xschem")
            if found is None:
                raise FileNotFoundError(
                    "xschem binary not found on PATH. "
                    "Install xschem (e.g., apt install xschem) or pass binary= explicitly."
                )
            self._binary = Path(found)

    @property
    def binary(self) -> Path:
        """Path to the xschem executable."""
        return self._binary

    @property
    def version(self) -> str:
        """xschem version string."""
        result = self.run(["--version"])
        return result.stdout.strip()

    def netlist(
        self,
        schematic: str | Path,
        output_dir: str | Path | None = None,
        output_name: str | None = None,
        format: str = "spice",
    ) -> Path:
        """Generate a netlist from a schematic file.

        Args:
            schematic: Path to .sch file.
            output_dir: Directory for output. Uses temp dir if None.
            output_name: Output filename (name only). Derived from schematic if None.
            format: Netlist format — "spice", "verilog", or "vhdl".

        Returns:
            Path to the generated netlist file.
        """
        schematic = Path(schematic).resolve()

        if format not in _FORMAT_FLAGS:
            raise ValueError(f"Unknown format '{format}'. Use: {list(_FORMAT_FLAGS.keys())}")

        if output_dir is None:
            output_dir = Path(tempfile.mkdtemp(prefix="pyxschem_"))
        else:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)

        args = ["-n", _FORMAT_FLAGS[format], "-o", str(output_dir), "-q", str(schematic)]

        if output_name is not None:
            args = ["-n", _FORMAT_FLAGS[format], "-o", str(output_dir),
                    "-N", output_name, "-q", str(schematic)]

        self.run(args)

        # Determine output filename
        if output_name is not None:
            result_path = output_dir / output_name
        else:
            ext = {"spice": ".spice", "verilog": ".v", "vhdl": ".vhd"}[format]
            result_path = output_dir / (schematic.stem + ext)

        return result_path

    def command(self, tcl_cmd: str, schematic: str | Path | None = None) -> str:
        """Execute a Tcl command via xschem.

        Args:
            tcl_cmd: Tcl command string to execute.
            schematic: Optional schematic to load before executing.

        Returns:
            Command stdout.
        """
        args = ["--command", tcl_cmd, "-q"]
        if schematic is not None:
            args.append(str(Path(schematic).resolve()))
        result = self.run(args)
        return result.stdout

    def run(self, args: list[str]) -> subprocess.CompletedProcess:
        """Run xschem with arbitrary arguments.

        Always includes -x (headless, no X display).
        """
        cmd = [str(self._binary), "-x"] + args
        return subprocess.run(cmd, capture_output=True, text=True)
