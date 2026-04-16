"""Shared container mixin for Schematic and Symbol."""

from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path

from pyxschem.model import Arc, Box, GraphicLine, Header, Polygon, Text
from pyxschem.parser import serialize_schematic


class _ElementContainerMixin:
    """Shared element-container methods for Schematic and Symbol.

    Subclasses must override ``_make_default_header``.
    """

    _elements: list  # list[Element]
    _path: Path | None

    def _make_default_header(self, version: str, file_version: str) -> Header:
        raise NotImplementedError

    # -- Properties --

    @property
    def elements(self) -> list:
        """All elements in this container (read-only view)."""
        return self._elements

    @property
    def path(self) -> Path | None:
        """File path this was loaded from, or None."""
        return self._path

    @property
    def header(self) -> Header | None:
        for e in self._elements:
            if isinstance(e, Header):
                return e
        return None

    @property
    def texts(self) -> list[Text]:
        return [e for e in self._elements if isinstance(e, Text)]

    @property
    def lines(self) -> list[GraphicLine]:
        return [e for e in self._elements if isinstance(e, GraphicLine)]

    @property
    def boxes(self) -> list[Box]:
        return [e for e in self._elements if isinstance(e, Box)]

    @property
    def arcs(self) -> list[Arc]:
        return [e for e in self._elements if isinstance(e, Arc)]

    @property
    def polygons(self) -> list[Polygon]:
        return [e for e in self._elements if isinstance(e, Polygon)]

    # -- Mutation --

    def set_version(self, version: str, file_version: str = "1.2") -> None:
        """Set the xschem version header, creating one if needed."""
        v_line = f"v {{xschem version={version} file_version={file_version}}}"
        header = self.header
        if header is None:
            self._elements.insert(0, self._make_default_header(version, file_version))
            return
        for i, line in enumerate(header.raw_lines):
            if line.startswith("v "):
                header.raw_lines[i] = v_line
                return
        header.raw_lines.insert(0, v_line)

    def add_line(
        self,
        layer: int,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        attributes: dict[str, str] | None = None,
    ) -> GraphicLine:
        """Add a graphical line."""
        item = GraphicLine(
            layer=layer,
            x1=x1,
            y1=y1,
            x2=x2,
            y2=y2,
            attributes=attributes or {},
        )
        self._elements.append(item)
        return item

    def add_box(
        self,
        layer: int,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        attributes: dict[str, str] | None = None,
    ) -> Box:
        """Add a graphical box."""
        item = Box(
            layer=layer,
            x1=x1,
            y1=y1,
            x2=x2,
            y2=y2,
            attributes=attributes or {},
        )
        self._elements.append(item)
        return item

    def add_arc(
        self,
        layer: int,
        x: float,
        y: float,
        r: float,
        start_angle: float,
        sweep_angle: float,
        attributes: dict[str, str] | None = None,
    ) -> Arc:
        """Add a graphical arc."""
        item = Arc(
            layer=layer,
            x=x,
            y=y,
            r=r,
            start_angle=start_angle,
            sweep_angle=sweep_angle,
            attributes=attributes or {},
        )
        self._elements.append(item)
        return item

    def add_polygon(
        self,
        layer: int,
        points: list[tuple[float, float]],
        attributes: dict[str, str] | None = None,
    ) -> Polygon:
        """Add a polygon."""
        item = Polygon(layer=layer, points=list(points), attributes=attributes or {})
        self._elements.append(item)
        return item

    # -- I/O --

    def to_text(self) -> str:
        """Serialize to a string."""
        return serialize_schematic(self._elements)

    def save(self, path: str | Path | None = None) -> None:
        """Write to a file (atomic write with permission preservation)."""
        if path is not None:
            p = Path(path)
        elif self._path is not None:
            p = self._path
        else:
            raise ValueError("No path specified and file was not loaded from disk")
        original_mode = None
        if p.exists():
            original_mode = stat.S_IMODE(os.stat(p).st_mode)
        fd, tmp = tempfile.mkstemp(dir=p.parent, suffix=".tmp")
        try:
            if original_mode is not None:
                os.fchmod(fd, original_mode)
            with open(fd, "w", encoding="utf-8") as f:
                f.write(self.to_text())
            Path(tmp).replace(p)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
