"""Shared fixtures and constants for pyxschem tests."""

import shutil
from pathlib import Path

import pytest

from pyxschem import SymbolLibrary

HAS_XSCHEM = shutil.which("xschem") is not None
SYSTEM_DEVICES_DIR = Path("/usr/share/xschem/xschem_library")
SYSTEM_EXAMPLES = Path("/usr/share/doc/xschem/examples")


@pytest.fixture
def system_libs():
    """SymbolLibrary backed by the real xschem system library."""
    return SymbolLibrary([SYSTEM_DEVICES_DIR])
