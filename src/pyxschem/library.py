"""Library resolution for xschem symbol paths.

Parses xschemrc configuration files to discover XSCHEM_LIBRARY_PATH,
then resolves symbol references (e.g., "devices/res.sym") to filesystem
paths and loads them as Symbol instances.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from pyxschem.symbol import Symbol


class XschemConfig:
    """Parsed xschemrc configuration.

    Extracts XSCHEM_LIBRARY_PATH from xschemrc files using a minimal
    Tcl subset parser (set, append, variable substitution).
    """

    def __init__(self, library_paths: list[Path]) -> None:
        self._library_paths = library_paths

    @classmethod
    def load(cls, path: str | Path) -> XschemConfig:
        """Parse an xschemrc file."""
        p = Path(path)
        text = p.read_text(encoding="utf-8")
        paths = _parse_xschemrc(text, base_dir=p.parent)
        return cls(paths)

    @classmethod
    def from_paths(cls, paths: list[str | Path]) -> XschemConfig:
        """Create config from explicit library paths."""
        return cls([Path(p) for p in paths])

    @property
    def library_paths(self) -> list[Path]:
        """Resolved library search paths."""
        return list(self._library_paths)


class SymbolLibrary:
    """Resolve and cache xschem symbols from library paths.

    Usage::

        config = XschemConfig.load("xschemrc")
        libs = SymbolLibrary.from_config(config)
        sym = libs.resolve("devices/res.sym")
        matches = libs.search("nfet")
    """

    def __init__(self, paths: list[Path]) -> None:
        self._paths = paths
        self._cache: dict[str, Symbol | None] = {}

    @property
    def paths(self) -> list[Path]:
        """Library search paths."""
        return list(self._paths)

    @classmethod
    def from_config(cls, config: XschemConfig) -> SymbolLibrary:
        """Create library from parsed config."""
        return cls(config.library_paths)

    def resolve(self, symbol_ref: str) -> Symbol | None:
        """Resolve a symbol reference to a Symbol instance.

        Both subpath (``"devices/res.sym"``) and basename
        (``"res.sym"``) forms are accepted, matching xschem's resolver.
        See :meth:`_candidates_for` for the layout-based fallback.
        Results (including misses) are cached.
        """
        if symbol_ref in self._cache:
            return self._cache[symbol_ref]

        ref_parts = Path(symbol_ref).parts

        for base in self._paths:
            for candidate in self._candidates_for(base, symbol_ref, ref_parts):
                if not candidate.resolve().is_relative_to(base.resolve()):
                    continue
                if candidate.is_file():
                    sym = Symbol.load(candidate)
                    self._cache[symbol_ref] = sym
                    return sym

        self._cache[symbol_ref] = None
        return None

    @staticmethod
    def _candidates_for(
        base: Path, symbol_ref: str, ref_parts: tuple[str, ...]
    ) -> list[Path]:
        """Plausible filesystem locations for a symbol_ref under base."""
        candidates = [base / symbol_ref]
        # If symbol_ref has a leading dir that matches the base name,
        # the base already represents that dir — try the basename too.
        if len(ref_parts) > 1 and ref_parts[0] == base.name:
            candidates.append(base / Path(*ref_parts[1:]))
        return candidates

    def search(self, query: str) -> list[str]:
        """Search for symbols matching a query string.

        Case-insensitive substring match against symbol filenames.

        Args:
            query: Search string, e.g. "nfet" or "res"

        Returns:
            List of matching symbol references (relative paths).
        """
        query_lower = query.lower()
        results: list[str] = []

        for base in self._paths:
            if not base.is_dir():
                continue
            for sym_path in sorted(base.rglob("*.sym")):
                ref = str(sym_path.relative_to(base))
                if query_lower in ref.lower() and ref not in results:
                    results.append(ref)

        return results

    def list_symbols(self) -> list[str]:
        """List all available symbol references."""
        return self.search("")


# -- xschemrc parsing --

_VAR_PATTERN = re.compile(r"\$\{(\w+)\}|\$env\((\w+)\)|\$(\w+)")


def _parse_xschemrc(text: str, base_dir: Path | None = None) -> list[Path]:
    """Parse xschemrc text and extract XSCHEM_LIBRARY_PATH entries.

    Handles the Tcl subset:
    - set VAR value
    - append VAR :path
    - $VAR, ${VAR} substitution
    - $env(NAME) environment variable access
    - # comments
    """
    variables: dict[str, str] = {}

    # Seed with environment defaults
    if "XSCHEM_SHAREDIR" in os.environ:
        variables["XSCHEM_SHAREDIR"] = os.environ["XSCHEM_SHAREDIR"]
    if "USER_CONF_DIR" not in variables:
        variables["USER_CONF_DIR"] = str(Path.home() / ".xschem")

    for line in text.splitlines():
        line = line.strip()

        # Skip comments and empty lines
        if not line or line.startswith("#"):
            continue

        parts = line.split(None, 2)
        if len(parts) < 2:
            continue

        cmd = parts[0]

        if cmd == "set" and len(parts) >= 3:
            var_name = parts[1]
            raw_value = parts[2]
            # Tcl {} means empty string
            if raw_value == "{}":
                raw_value = ""
            value = _substitute_vars(raw_value, variables)
            variables[var_name] = value

        elif cmd == "append" and len(parts) >= 3:
            var_name = parts[1]
            raw_value = _substitute_vars(parts[2], variables)
            existing = variables.get(var_name, "")
            variables[var_name] = existing + raw_value

    # Extract XSCHEM_LIBRARY_PATH
    lib_path_str = variables.get("XSCHEM_LIBRARY_PATH", "")
    if not lib_path_str:
        return []

    # Split on : (or ; on Windows)
    separator = ";" if os.name == "nt" else ":"
    raw_paths = [p for p in lib_path_str.split(separator) if p.strip()]

    # Resolve to Path objects
    result: list[Path] = []
    for p in raw_paths:
        path = Path(p.strip())
        if not path.is_absolute() and base_dir is not None:
            path = base_dir / path
        result.append(path)

    return result


def _substitute_vars(text: str, variables: dict[str, str]) -> str:
    """Substitute $VAR, ${VAR}, and $env(NAME) in text."""

    def _replace(match: re.Match[str]) -> str:
        whole = match.group(0)
        braced = match.group(1)
        env_name = match.group(2)
        bare = match.group(3)
        if braced:
            return variables.get(braced, whole)
        if env_name:
            return os.environ.get(env_name, whole)
        if bare:
            return variables.get(bare, whole)
        return whole

    return _VAR_PATTERN.sub(_replace, text)
