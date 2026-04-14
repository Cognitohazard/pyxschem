"""Shared fixtures and constants for pyxschem tests."""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from pyxschem import SymbolLibrary
from pyxschem.symbol import Pin, Symbol

HAS_XSCHEM = shutil.which("xschem") is not None
SYSTEM_DEVICES_DIR = Path("/usr/share/xschem/xschem_library")
SYSTEM_EXAMPLES = Path("/usr/share/doc/xschem/examples")


@pytest.fixture
def system_libs():
    """SymbolLibrary backed by the real xschem system library."""
    return SymbolLibrary([SYSTEM_DEVICES_DIR])


def mock_libs(*pairs: tuple[str, Symbol]) -> MagicMock:
    """Create a mock SymbolLibrary from (symbol_name, Symbol) pairs."""
    lookup = dict(pairs)
    libs = MagicMock()
    libs.resolve.side_effect = lambda name: lookup.get(name)
    return libs


def make_symbol(
    x1: float = -10,
    y1: float = -10,
    x2: float = 10,
    y2: float = 10,
    pins: list[Pin] | None = None,
) -> Symbol:
    """Create a Symbol with a box body and optional pins."""
    sym = Symbol.new()
    sym.add_box(4, x1, y1, x2, y2)
    for p in pins or []:
        sym.add_pin(p.name, p.direction, p.x, p.y)
    return sym
