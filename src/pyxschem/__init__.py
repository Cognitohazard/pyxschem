"""pyxschem — Python library for xschem schematic files."""

__version__ = "0.1.0"

from pyxschem.attributes import parse_attributes, serialize_attributes
from pyxschem.cli import XschemCLI
from pyxschem.diff import (
    ComponentChange,
    NetChange,
    SchemDiff,
    TextChange,
    diff_schematics,
)
from pyxschem.hierarchy import HierarchyNode
from pyxschem.library import SymbolLibrary, XschemConfig
from pyxschem.model import Component, Header, Net, Text
from pyxschem.schematic import Schematic
from pyxschem.symbol import Pin, Symbol
from pyxschem.validate import ValidationIssue, ValidationResult, validate

__all__ = [
    "Component",
    "ComponentChange",
    "Header",
    "HierarchyNode",
    "Net",
    "NetChange",
    "Pin",
    "SchemDiff",
    "Schematic",
    "Symbol",
    "SymbolLibrary",
    "Text",
    "TextChange",
    "ValidationIssue",
    "ValidationResult",
    "XschemCLI",
    "XschemConfig",
    "diff_schematics",
    "parse_attributes",
    "serialize_attributes",
    "validate",
]
