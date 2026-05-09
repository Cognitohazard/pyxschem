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

# Sentinel emitted by the catch-wrapper around user Tcl in command()
# / session() so we can detect Tcl-level failures even when xschem
# exits 0.
_TCL_ERROR_SENTINEL = "__PYXSCHEM_TCL_ERROR__:"

# Default subprocess timeout. xschem on a malformed argument list can
# wedge silently (e.g. `xschem -x --bad-flag` never returns), so we
# refuse to wait forever by default. Override via timeout= per call;
# pass timeout=0 (or any non-positive value) to disable.
DEFAULT_TIMEOUT_S: float = 120.0


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
        rcfile: str | Path | None = None,
        no_rcload: bool = False,
        timeout: float | None = DEFAULT_TIMEOUT_S,
    ) -> Path:
        """Generate a netlist from a schematic file.

        Args:
            schematic: Path to .sch file. If ``cwd`` is set and this is
                a relative path, it is resolved by xschem against
                ``cwd``; otherwise it is resolved against the calling
                process's working directory.
            output_dir: Directory for output. Resolved to absolute
                before being passed to xschem so it lands in the
                expected location regardless of ``cwd``. Uses temp
                dir if None.
            output_name: Output filename (name only). Derived from
                schematic if None.
            format: Netlist format — "spice", "verilog", or "vhdl".
            env: Optional environment overlay merged onto
                ``os.environ`` (e.g. ``XSCHEM_LIBRARY_PATH``). Note
                that env= alone does **not** isolate the build from
                the host ``xschemrc`` — that file is read on startup
                independently. For full isolation pass ``no_rcload=
                True`` or ``rcfile=`` together with the env overlay.
            cwd: Optional working directory for the xschem invocation.
            rcfile: Use this file as xschem's startup rc instead of
                the default ``xschemrc``. Pairs with ``env=`` to give
                a fully isolated build.
            no_rcload: If true, xschem skips loading any rc file
                (``-i`` / ``--no_rcload``). Useful for tests that
                must not depend on the host config.
            timeout: Hard subprocess timeout (seconds). Defaults to
                ``DEFAULT_TIMEOUT_S`` (120 s) so a
                misbehaving xschem can't hang the caller forever.
                Pass ``None`` to disable, or a smaller number for
                test suites.

        Returns:
            Path to the generated netlist file.

        Raises:
            RuntimeError: When xschem exits non-zero, or exits zero but
                the produced netlist contains ``IS MISSING`` placeholders
                or its output stream contains a Tcl evaluation error.
                xschem itself silently ignores both — pyxschem surfaces
                them so consumers don't ship broken netlists.
            subprocess.TimeoutExpired: When ``timeout`` elapses.
        """
        sch_path = Path(schematic)
        if cwd is None:
            sch_path = sch_path.resolve()

        if format not in _FORMAT_FLAGS:
            raise ValueError(
                f"Unknown format '{format}'. Use: {list(_FORMAT_FLAGS.keys())}"
            )

        if output_dir is None:
            output_dir = Path(tempfile.mkdtemp(prefix="pyxschem_"))
        else:
            output_dir = Path(output_dir).resolve()
            output_dir.mkdir(parents=True, exist_ok=True)

        args = ["-n", _FORMAT_FLAGS[format], "-o", str(output_dir)]
        if output_name is not None:
            args += ["-N", output_name]
        args += ["-q", str(sch_path)]

        result = self.run(
            args,
            env=env,
            cwd=cwd,
            rcfile=rcfile,
            no_rcload=no_rcload,
            timeout=timeout,
        )
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
            result_path = output_dir / (sch_path.stem + ext)

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
        rcfile: str | Path | None = None,
        no_rcload: bool = False,
        timeout: float | None = DEFAULT_TIMEOUT_S,
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
            rcfile=rcfile,
            no_rcload=no_rcload,
            timeout=timeout,
        )
        return path.read_text(encoding="utf-8")

    @contextmanager
    def session(
        self,
        schematic: str | Path | None = None,
        *,
        env: dict[str, str] | None = None,
        cwd: str | Path | None = None,
        rcfile: str | Path | None = None,
        no_rcload: bool = False,
        timeout: float | None = DEFAULT_TIMEOUT_S,
    ) -> Iterator[_XschemSession]:
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
        Each queued command is wrapped in ``catch`` so a Tcl-level
        failure raises ``RuntimeError`` on flush.
        """
        sess = _XschemSession(
            self,
            schematic=schematic,
            env=env,
            cwd=cwd,
            rcfile=rcfile,
            no_rcload=no_rcload,
            timeout=timeout,
        )
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
        rcfile: str | Path | None = None,
        no_rcload: bool = False,
        timeout: float | None = DEFAULT_TIMEOUT_S,
    ) -> str:
        """Execute a Tcl command via xschem.

        .. warning::
            ``tcl_cmd`` is passed directly to the xschem Tcl interpreter.
            Never pass unsanitised user input — Tcl can execute arbitrary
            system commands (e.g. ``exec``).

        Args:
            tcl_cmd: Tcl command string to execute.
            schematic: Optional schematic to load before executing.
                Resolved against ``cwd`` if given, otherwise against
                the calling process's working directory.
            env, cwd, rcfile, no_rcload, timeout: see :meth:`netlist`.

        Returns:
            Command stdout (excluding the wrapper's error sentinel).

        Raises:
            RuntimeError: When xschem exits non-zero, or when the user
                command raises a Tcl-level error (xschem catches Tcl
                errors at the top level and exits 0; the wrapper
                surfaces them via stderr + a sentinel string).
        """
        wrapped = _wrap_tcl_with_catch(tcl_cmd)
        args = ["--command", wrapped, "-q"]
        if schematic is not None:
            sch_path = Path(schematic)
            if cwd is None:
                sch_path = sch_path.resolve()
            args.append(str(sch_path))
        result = self.run(
            args,
            env=env,
            cwd=cwd,
            rcfile=rcfile,
            no_rcload=no_rcload,
            timeout=timeout,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"xschem command failed (exit code {result.returncode}):\n"
                f"{result.stderr}"
            )
        if _TCL_ERROR_SENTINEL in result.stderr:
            preceding, _, tcl_msg = result.stderr.partition(_TCL_ERROR_SENTINEL)
            details = tcl_msg.strip()
            if preceding.strip():
                details = f"{details}\n--- preceding stderr ---\n{preceding.rstrip()}"
            raise RuntimeError(f"xschem Tcl command raised an error: {details}")
        return result.stdout

    def run(
        self,
        args: list[str],
        env: dict[str, str] | None = None,
        cwd: str | Path | None = None,
        rcfile: str | Path | None = None,
        no_rcload: bool = False,
        timeout: float | None = DEFAULT_TIMEOUT_S,
    ) -> subprocess.CompletedProcess:
        """Run xschem with arbitrary arguments.

        Always prepends ``-x`` (headless, no X display). Optional
        ``--rcfile`` / ``-i`` flags are inserted before the caller's
        ``args`` so they take effect during xschemrc loading.

        Args:
            args: Argument list passed to xschem (after the headless
                + isolation flags).
            env: Optional environment overlay merged onto
                ``os.environ``. Note that env alone does not isolate
                the run from the host ``xschemrc`` — pair with
                ``rcfile=`` or ``no_rcload=True`` for full isolation.
            cwd: Optional working directory.
            rcfile: Use this rc file instead of the default xschemrc
                (``--rcfile <file>``).
            no_rcload: Skip rc loading entirely (``-i``).
            timeout: Hard subprocess timeout (seconds). Defaults to
                ``_DEFAULT_TIMEOUT_S`` to refuse silent hangs (xschem
                wedges on some malformed flag combinations). Pass
                ``None`` to disable.

        Raises:
            subprocess.TimeoutExpired: when the timeout elapses.
        """
        head: list[str] = [str(self._binary), "-x"]
        if no_rcload:
            head.append("-i")
        if rcfile is not None:
            head += ["--rcfile", str(rcfile)]
        cmd = [*head, *args]

        merged_env: dict[str, str] | None = None
        if env is not None or cwd is not None:
            merged_env = {**os.environ, **(env or {})}
            # xschem resolves relative input paths against $PWD, not
            # the OS-level cwd, so we have to align them by hand.
            if cwd is not None:
                merged_env["PWD"] = str(Path(cwd).resolve())

        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=merged_env,
            cwd=str(cwd) if cwd is not None else None,
            timeout=None if timeout is None or timeout <= 0 else timeout,
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
        rcfile: str | Path | None = None,
        no_rcload: bool = False,
        timeout: float | None = DEFAULT_TIMEOUT_S,
    ) -> None:
        self._cli = cli
        self._schematic = schematic
        self._env = env
        self._cwd = cwd
        self._rcfile = rcfile
        self._no_rcload = no_rcload
        self._timeout: float | None = timeout
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
            rcfile=self._rcfile,
            no_rcload=self._no_rcload,
            timeout=self._timeout,
        )


def _wrap_tcl_with_catch(tcl_cmd: str) -> str:
    """Wrap a user-supplied Tcl command in ``catch`` so failures are
    surfaced via stderr + a sentinel rather than swallowed by xschem's
    top-level Tcl runner (which exits 0 even on an ``error``).

    Requires the user's Tcl to have balanced braces — Tcl's
    brace-quoting forbids unbalanced braces and backslash escapes
    don't apply inside ``{...}``. Raises ValueError otherwise.
    """
    depth = 0
    for ch in tcl_cmd:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                break
    if depth != 0:
        raise ValueError(
            "Tcl command has unbalanced braces — pyxschem wraps user "
            "Tcl in `catch {...}` and Tcl brace-quoting cannot represent "
            "unbalanced braces. Pre-balance the command or use \\u007b "
            "/ \\u007d escapes inside double-quoted Tcl strings."
        )
    return (
        f"if {{[catch {{{tcl_cmd}}} __pyxschem_err]}} {{ "
        f'puts stderr "{_TCL_ERROR_SENTINEL}$__pyxschem_err"; exit 1 '
        f"}}"
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
