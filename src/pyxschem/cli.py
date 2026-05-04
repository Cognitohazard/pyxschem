"""Thin wrapper for the xschem binary.

Delegates netlisting and batch commands to xschem — does not
reimplement xschem behavior. Follows the spicelib pattern:
Editor (pyxschem) + SimRunner (xschem CLI).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

_FORMAT_FLAGS = {
    "spice": "-s",
    "verilog": "-w",
    "vhdl": "-V",
}

# Markers in xschem output that we treat as failure even when xschem
# itself exits 0. Matches xschem 3.4.x.
_MISSING_SYMBOL_MARKER = re.compile(r"\bIS MISSING !!!!", re.IGNORECASE)
_TCL_ERROR_MARKERS = (
    "tclvareval(): error",
    "tcleval(): error",
    "missing close-brace",
)


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
                    "Install xschem (e.g., apt install xschem) "
                    "or pass binary= explicitly."
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
        env: dict[str, str] | None = None,
        cwd: str | Path | None = None,
    ) -> Path:
        """Generate a netlist from a schematic file.

        Args:
            schematic: Path to .sch file.
            output_dir: Directory for output. Uses temp dir if None.
            output_name: Output filename (name only). Derived from schematic if None.
            format: Netlist format — "spice", "verilog", or "vhdl".
            env: Optional environment overlay. Useful for setting
                ``XSCHEM_LIBRARY_PATH`` for an isolated build.
            cwd: Optional working directory for the xschem invocation.

        Returns:
            Path to the generated netlist file.

        Raises:
            RuntimeError: When xschem exits non-zero, or exits zero but
                the produced netlist contains ``IS MISSING`` placeholders
                or its output stream contains a Tcl evaluation error.
                xschem itself silently ignores both — pyxschem surfaces
                them so consumers don't ship broken netlists.
        """
        schematic = Path(schematic).resolve()

        if format not in _FORMAT_FLAGS:
            raise ValueError(
                f"Unknown format '{format}'. Use: {list(_FORMAT_FLAGS.keys())}"
            )

        if output_dir is None:
            output_dir = Path(tempfile.mkdtemp(prefix="pyxschem_"))
        else:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)

        args = ["-n", _FORMAT_FLAGS[format], "-o", str(output_dir)]
        if output_name is not None:
            args += ["-N", output_name]
        args += ["-q", str(schematic)]

        result = self.run(args, env=env, cwd=cwd)
        if result.returncode != 0:
            raise RuntimeError(
                f"xschem netlist failed (exit code {result.returncode}):\n"
                f"{result.stderr or result.stdout}"
            )

        # Determine output filename
        if output_name is not None:
            result_path = output_dir / output_name
        else:
            ext = {"spice": ".spice", "verilog": ".v", "vhdl": ".vhd"}[format]
            result_path = output_dir / (schematic.stem + ext)

        _check_netlist_health(result_path, result.stdout, result.stderr)

        return result_path

    def netlist_text(
        self,
        schematic: str | Path,
        *,
        output_dir: str | Path | None = None,
        format: str = "spice",
        env: dict[str, str] | None = None,
        cwd: str | Path | None = None,
    ) -> str:
        """Same as :meth:`netlist` but returns the file's text.

        Equivalent to ``self.netlist(...).read_text(encoding="utf-8")``;
        provided because most callers want the content, not the path.
        """
        path = self.netlist(
            schematic,
            output_dir=output_dir,
            format=format,
            env=env,
            cwd=cwd,
        )
        return path.read_text(encoding="utf-8")

    @contextmanager
    def session(
        self,
        schematic: str | Path | None = None,
        *,
        env: dict[str, str] | None = None,
        cwd: str | Path | None = None,
    ) -> "Iterator[_XschemSession]":
        """Buffer multiple Tcl commands into a single xschem invocation.

        xschem has no long-running headless mode, so each
        :meth:`command` call costs a process startup. A session
        accumulates Tcl commands and executes them in one shot when
        the context exits, amortising the cost::

            with cli.session(schematic="amp.sch") as s:
                s.run_tcl("puts [xschem get instances]")
                s.run_tcl("xschem get current_name")

            print(s.stdout)   # combined output of both commands

        ``schematic`` is loaded once before the buffered commands run.
        """
        sess = _XschemSession(self, schematic=schematic, env=env, cwd=cwd)
        try:
            yield sess
        finally:
            sess.flush()

    def command(
        self,
        tcl_cmd: str,
        schematic: str | Path | None = None,
        env: dict[str, str] | None = None,
        cwd: str | Path | None = None,
    ) -> str:
        """Execute a Tcl command via xschem.

        .. warning::
            ``tcl_cmd`` is passed directly to the xschem Tcl interpreter.
            Never pass unsanitised user input — Tcl can execute arbitrary
            system commands (e.g. ``exec``).

        Args:
            tcl_cmd: Tcl command string to execute.
            schematic: Optional schematic to load before executing.

        Returns:
            Command stdout.
        """
        args = ["--command", tcl_cmd, "-q"]
        if schematic is not None:
            args.append(str(Path(schematic).resolve()))
        result = self.run(args, env=env, cwd=cwd)
        if result.returncode != 0:
            raise RuntimeError(
                f"xschem command failed (exit code {result.returncode}):\n"
                f"{result.stderr}"
            )
        return result.stdout

    def run(
        self,
        args: list[str],
        env: dict[str, str] | None = None,
        cwd: str | Path | None = None,
    ) -> subprocess.CompletedProcess:
        """Run xschem with arbitrary arguments.

        Always includes -x (headless, no X display).

        Args:
            args: Argument list passed to xschem (after ``-x``).
            env: Optional environment overlay merged onto ``os.environ``.
                Pass e.g. ``{"XSCHEM_LIBRARY_PATH": ...}`` to isolate a
                build from the host config.
            cwd: Optional working directory.
        """
        cmd = [str(self._binary), "-x", *args]
        merged_env = None
        if env is not None:
            merged_env = {**os.environ, **env}
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=merged_env,
            cwd=str(cwd) if cwd is not None else None,
        )


class _XschemSession:
    """Buffer-and-flush session created via :meth:`XschemCLI.session`.

    Tcl commands queued with :meth:`run_tcl` are joined with ``;`` and
    executed in a single xschem invocation when the surrounding
    context exits (or on an explicit :meth:`flush`). The combined
    output is available on :attr:`stdout` after flushing.
    """

    def __init__(
        self,
        cli: XschemCLI,
        *,
        schematic: str | Path | None = None,
        env: dict[str, str] | None = None,
        cwd: str | Path | None = None,
    ) -> None:
        self._cli = cli
        self._schematic = schematic
        self._env = env
        self._cwd = cwd
        self._buffer: list[str] = []
        self.stdout: str = ""
        self._flushed = False

    def run_tcl(self, tcl: str) -> None:
        """Queue a Tcl command; executed when the session is flushed."""
        if self._flushed:
            raise RuntimeError("session is already flushed; create a new one")
        self._buffer.append(tcl)

    def flush(self) -> None:
        """Execute every queued Tcl command in a single xschem run."""
        if self._flushed:
            return
        self._flushed = True
        if not self._buffer:
            return
        self.stdout = self._cli.command(
            "; ".join(self._buffer),
            schematic=self._schematic,
            env=self._env,
            cwd=self._cwd,
        )


def _check_netlist_health(path: Path, stdout: str, stderr: str) -> None:
    """Raise if xschem produced a netlist that's silently broken."""
    body = path.read_text(encoding="utf-8") if path.is_file() else ""

    if _MISSING_SYMBOL_MARKER.search(body):
        bad_lines = [ln for ln in body.splitlines() if "IS MISSING" in ln]
        raise RuntimeError(
            "xschem produced a netlist with unresolved symbols. Check "
            "XSCHEM_LIBRARY_PATH or pass env={'XSCHEM_LIBRARY_PATH': ...} "
            f"to XschemCLI.netlist().\n  netlist: {path}\n"
            + "\n".join(f"  {ln}" for ln in bad_lines[:10])
        )

    combined = f"{stdout or ''}\n{stderr or ''}"
    for marker in _TCL_ERROR_MARKERS:
        if marker in combined:
            raise RuntimeError(
                f"xschem reported a Tcl evaluation error during netlisting "
                f"(marker: {marker!r}). The netlist at {path} is likely "
                f"missing components.\n--- xschem output ---\n"
                f"{combined.strip()[-1200:]}"
            )
