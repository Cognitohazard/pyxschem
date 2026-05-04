"""pyxschem — Python library for xschem schematic files."""

try:
    from pyxschem._version import __version__
except ModuleNotFoundError:
    __version__ = "0.0.0+unknown"

from pyxschem.attributes import parse_attributes, serialize_attributes
from pyxschem.audit import (
    DEFAULT_VALUE_PREFIXES,
    FileReport,
    ProjectReport,
    audit_tree,
)
from pyxschem.cli import XschemCLI
from pyxschem.connectivity import (
    NetAnalyzer,
    NetConnection,
    connectivity_from_netlist,
    connectivity_from_schematic,
)
from pyxschem.diff import (
    ComponentChange,
    NetChange,
    SchemDiff,
    TextChange,
    diff_schematics,
)
from pyxschem.geometry import BBox, GeometryQuery
from pyxschem.hierarchy import HierarchyNode
from pyxschem.library import SymbolLibrary, XschemConfig
from pyxschem.model import (
    Arc,
    Box,
    Component,
    GraphicLine,
    Header,
    Net,
    Polygon,
    RawLine,
    Text,
)
from pyxschem.schematic import BomEntry, Schematic, SubcircuitPort
from pyxschem.symbol import Pin, Symbol
from pyxschem.validate import ValidationIssue, ValidationResult, Validator, validate

__all__ = [
    "DEFAULT_VALUE_PREFIXES",
    "Arc",
    "BBox",
    "BomEntry",
    "Box",
    "Component",
    "ComponentChange",
    "FileReport",
    "GeometryQuery",
    "GraphicLine",
    "Header",
    "HierarchyNode",
    "Net",
    "NetAnalyzer",
    "NetChange",
    "NetConnection",
    "Pin",
    "Polygon",
    "ProjectReport",
    "RawLine",
    "SchemDiff",
    "Schematic",
    "SubcircuitPort",
    "Symbol",
    "SymbolLibrary",
    "Text",
    "TextChange",
    "ValidationIssue",
    "ValidationResult",
    "Validator",
    "XschemCLI",
    "XschemConfig",
    "audit_tree",
    "connectivity_from_netlist",
    "connectivity_from_schematic",
    "diff_schematics",
    "parse_attributes",
    "serialize_attributes",
    "validate",
]
