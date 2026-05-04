"""Project-tree audit for collections of xschem schematics.

A CI-style roll-up that walks a directory of ``.sch`` files and
surfaces:

* components referencing a symbol the library cannot resolve
* components whose name implies a passive (R / L / C / I / V) but
  carry no ``value`` attribute
* components missing a ``name`` entirely (would emit as ``?`` to
  xschem)
* per-file validation issue counts

Provides :func:`audit_tree` and the :class:`ProjectReport` /
:class:`FileReport` data classes. Schematic-only — no SPICE.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from pyxschem.schematic import Schematic
from pyxschem.validate import validate

DEFAULT_VALUE_PREFIXES: frozenset[str] = frozenset({"R", "L", "C", "I", "V"})


@dataclass
class FileReport:
    """Per-file audit result."""

    path: Path
    n_components: int = 0
    unresolved_symbols: Counter[str] = field(default_factory=Counter)
    missing_value: list[str] = field(default_factory=list)
    missing_name: list[str] = field(default_factory=list)
    validation_errors: int = 0
    validation_warnings: int = 0

    @property
    def is_clean(self) -> bool:
        return not (
            self.unresolved_symbols
            or self.missing_value
            or self.missing_name
            or self.validation_errors
        )


@dataclass
class ProjectReport:
    """Aggregated audit across a directory of schematics."""

    files: list[FileReport] = field(default_factory=list)

    @property
    def n_files(self) -> int:
        return len(self.files)

    @property
    def total_unresolved(self) -> int:
        return sum(sum(f.unresolved_symbols.values()) for f in self.files)

    @property
    def total_missing_value(self) -> int:
        return sum(len(f.missing_value) for f in self.files)

    @property
    def total_missing_name(self) -> int:
        return sum(len(f.missing_name) for f in self.files)

    @property
    def total_validation_errors(self) -> int:
        return sum(f.validation_errors for f in self.files)

    @property
    def is_clean(self) -> bool:
        return all(f.is_clean for f in self.files)

    def unresolved_by_symbol(self) -> dict[str, list[Path]]:
        """Group unresolved-symbol references by symbol → list of files."""
        out: defaultdict[str, list[Path]] = defaultdict(list)
        for f in self.files:
            for sym in f.unresolved_symbols:
                out[sym].append(f.path)
        return dict(out)

    def summary(self) -> str:
        """Multi-line human-readable summary, suitable for CI output."""
        lines: list[str] = []
        for f in self.files:
            marker = "OK" if f.is_clean else "BAD"
            lines.append(
                f"  [{marker}] {f.path.name}: comps={f.n_components} "
                f"unres={sum(f.unresolved_symbols.values())} "
                f"miss_val={len(f.missing_value)} "
                f"miss_name={len(f.missing_name)} "
                f"val_err={f.validation_errors}"
            )
        bad = sum(0 if f.is_clean else 1 for f in self.files)
        lines.append(f"  {bad}/{self.n_files} file(s) flagged")
        return "\n".join(lines)


def audit_tree(
    root: Path | str,
    libs,  # SymbolLibrary; lazy-typed to avoid a hard import here
    *,
    pattern: str = "*.sch",
    value_prefixes: Iterable[str] = DEFAULT_VALUE_PREFIXES,
    skip_validation: bool = False,
) -> ProjectReport:
    """Walk ``root`` for schematics matching ``pattern`` and audit each.

    Args:
        root: Directory to scan recursively.
        libs: SymbolLibrary used to resolve component symbols and to
            run :func:`pyxschem.validate.validate`.
        pattern: Glob applied via ``Path.rglob``.
        value_prefixes: Component-name first letters that imply a
            ``value`` attribute is required (defaults to passives:
            ``R L C I V``).
        skip_validation: If true, skip per-file
            :func:`pyxschem.validate.validate` (useful when the cost
            isn't justified or the library is incomplete).

    Returns:
        A :class:`ProjectReport`.
    """
    root_path = Path(root)
    prefixes = frozenset(value_prefixes)
    report = ProjectReport()
    for sch_path in sorted(root_path.rglob(pattern)):
        if not sch_path.is_file():
            continue
        rep = FileReport(path=sch_path)
        sch = Schematic.load(sch_path)
        rep.n_components = len(sch.components)
        for c in sch.components:
            if libs.resolve(c.symbol) is None:
                rep.unresolved_symbols[c.symbol] += 1
            if not c.name:
                rep.missing_name.append(c.symbol)
                continue
            if c.name[0] in prefixes and not c.attributes.get("value"):
                rep.missing_value.append(c.name)
        if not skip_validation:
            result = validate(sch, libs=libs)
            rep.validation_errors = sum(
                1 for i in result.issues if i.severity == "error"
            )
            rep.validation_warnings = sum(
                1 for i in result.issues if i.severity == "warning"
            )
        report.files.append(rep)
    return report
