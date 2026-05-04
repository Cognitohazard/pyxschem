# pyxschem

> **WIP** — This project is under active development. APIs may change without notice. Not yet recommended for production use.

Python library for reading, editing, and generating [xschem](https://xschem.sourceforge.io/) schematic (`.sch`) and symbol (`.sym`) files. Pure Python, zero runtime dependencies, round-trip faithful.

## Installation

```bash
uv add pyxschem
# or
pip install pyxschem
```

## Quick Start

```python
from pyxschem import Schematic

sch = Schematic.load("amplifier.sch")

# Query
r1 = sch.get_component("R1")
print(r1.value)       # "10k"
print(r1.position)    # (400, -200)

resistors = sch.get_components(prefix="R")
vdd_nets = sch.get_nets(label="VDD")

# Modify
sch.set_component_value("R1", "4.7k")
sch.set_component_attribute("R1", "m", "2")

# Add / remove
# Symbol references can be either a basename ("cap.sym") or a subpath
# ("devices/cap.sym"); both resolve as long as the library path covers
# the symbol's location.
sch.add_component("cap.sym", x=400, y=-200,
                   attributes={"name": "C1", "value": "100n"})
sch.remove_component("C3")

# Save (round-trip: unmodified elements are byte-identical)
sch.save("amplifier_modified.sch")
```

## Features

### Schematic I/O

Parse and serialize all `.sch` line types — components (`C`), nets (`N`), text (`T`), graphical elements (`L`, `B`, `A`, `P`), and header blocks (`v`, `G`, `K`, `V`, `S`, `E`). Round-trip load/save produces byte-identical output for unmodified elements.

```python
sch = Schematic.load("design.sch")
sch = Schematic.from_text(text_string)
sch = Schematic.new()

sch.save("output.sch")
text = sch.to_text()
```

### Symbol Support

Load `.sym` files, inspect pins, read SPICE format templates, and access default instance attributes.

```python
from pyxschem import Symbol

sym = Symbol.load("devices/res.sym")
sym.pins       # [Pin(name="P", direction="inout", x=0, y=-30), ...]
sym.type       # "resistor"
sym.format     # "@name @pinlist @value m=@m"
sym.template   # {"name": "R1", "value": "1k", "m": "1"}
```

### Library Resolution

Parse `xschemrc` configuration files to discover `XSCHEM_LIBRARY_PATH`, then resolve symbol references to filesystem paths. Supports Tcl variable substitution (`$VAR`, `${VAR}`, `$env(NAME)`).

```python
from pyxschem import XschemConfig, SymbolLibrary

config = XschemConfig.load("xschemrc")
libs = SymbolLibrary.from_config(config)

sym = libs.resolve("devices/res.sym")    # Symbol instance or None
matches = libs.search("nfet")            # ["devices/nfet.sym", ...]
all_syms = libs.list_symbols()
```

Or create a library from explicit paths:

```python
config = XschemConfig.from_paths(["/usr/share/xschem/xschem_library", "./symbols"])
libs = SymbolLibrary.from_config(config)
```

### Hierarchy Traversal

Walk the design hierarchy by recursively loading sub-schematics. Find components across all levels or flatten the tree to leaf primitives.

```python
nodes = sch.hierarchy(libs)
for node in nodes:
    print(node.path, node.symbol_path, node.is_subcircuit)

# Search across all hierarchy levels
mosfets = sch.find_all(libs, prefix="M")
nfets = sch.find_all(libs, symbol="nmos")

# Flatten to leaf components
all_primitives = sch.flatten(libs)
```

### Pin Geometry & Wiring

Compute pin positions in schematic coordinates (handles mirror, rotation, translation), label pins, and draw orthogonal wires between them.

```python
x, y = sch.pin_position("R1", "P", libs)

# Tag a pin with a net label — places a lab_pin.sym at the pin
# coordinate so xschem's netlister adopts the label.
sch.connect("M1", "g", "clk", libs)          # alias: sch.add_label_pin
sch.connect("M1", "d", "VDD", libs)

# The stock device library mixes upper/lower-case pin names; opt in
# to fold the difference.
sch.connect("C1", "p", "VOUT", libs, case_insensitive=True)

# Draw a wire — either by coordinates or by pin endpoints.
sch.add_net(100, -200, 300, -200)
sch.add_net(between=(("R1", "P"), ("R2", "M")), libs=libs)

# add_wire is a thin alias of the latter form.
sch.add_wire("R1", "P", "R2", "M", libs)
```

### Subcircuit authoring

```python
sch = Schematic.new()
sch.add_component("ipin.sym", x=100, y=-200, attributes={"name": "p1", "lab": "IN"})
sch.add_component("opin.sym", x=500, y=-200, attributes={"name": "p2", "lab": "OUT"})
# ... place internal devices ...

# Mark this file as a subcircuit so xschem expands parent X-instances.
sch.set_subcircuit_metadata(format="@name @pinlist @symname")

# Discover the port list (in declaration order) of a sub-schematic.
ports = sch.subcircuit_ports()
# [SubcircuitPort(name='IN', direction='in', x=100, y=-200), ...]
```

### Refactoring

```python
# Bulk attribute swap — PDK migration in one call.
sch.transform_components(
    symbol="nmos4.sym",
    attr_remap={"model": {"n": "nmos_lvt"}},
)

# Multi-key update on a single component.
sch.set_component_attributes("M1", w="2u", l="0.18u", m="4")

# General predicate/mutator.
sch.bulk_update(
    lambda c: c.symbol == "res.sym" and "footprint" not in c.attributes,
    lambda c: c.set_attribute("footprint", "0805"),
)
```

### Bill-of-materials

```python
for entry in sch.bom():
    print(entry.count, entry.symbol, entry.value, entry.footprint)

# Walk the hierarchy and roll up leaf components only.
deep = top.bom(libs=libs, flatten=True)
```

### Project audit

```python
from pyxschem import audit_tree

report = audit_tree("path/to/project", libs)
print(report.summary())
print(report.unresolved_by_symbol())   # {"missing.sym": [Path("a.sch"), ...]}
```

### Attribute Parsing

Parse and serialize xschem's Tcl-style attribute blocks — bare values, double-quoted, and brace-quoted with nesting.

```python
from pyxschem import parse_attributes, serialize_attributes

attrs = parse_attributes('{name=R1 value=10k m=1}')
# {"name": "R1", "value": "10k", "m": "1"}

text = serialize_attributes({"name": "V1", "value": "PWL(0 0 1n 1.8)"})
# '{name=V1 value={PWL(0 0 1n 1.8)}}'
```

### xschem CLI Wrapper

Drive the xschem binary for netlisting and Tcl commands. Requires xschem installed separately.

```python
from pyxschem import XschemCLI

cli = XschemCLI()                       # auto-detect binary
cli = XschemCLI(binary="/usr/bin/xschem")

# Generate netlist — returns a pathlib.Path
netlist_path = cli.netlist("amp.sch", format="spice", output_dir="build/")
print(netlist_path.read_text())

# Override the library search path for an isolated build
netlist_path = cli.netlist(
    "amp.sch",
    format="spice",
    output_dir="build/",
    env={"XSCHEM_LIBRARY_PATH": "/path/to/libs:/path/to/devices"},
)

# Get the netlist as text directly.
text = cli.netlist_text("amp.sch", output_dir="build/")

# Execute a single Tcl command.
output = cli.command("puts [xschem get instances]", schematic="amp.sch")

# Or buffer multiple Tcl commands into one xschem invocation.
with cli.session(schematic="amp.sch") as s:
    s.run_tcl("puts [xschem get current_name]")
    s.run_tcl("puts [xschem get instances]")
print(s.stdout)
```

`netlist()` raises `RuntimeError` when xschem silently emits a broken
netlist (unresolved symbols or a Tcl-evaluation error), so consumers
do not unknowingly ship `IS MISSING !!!!` placeholders.

## API Reference

### Core Classes

| Class | Description |
|-|-|
| `Schematic` | Load, query, modify, and save `.sch` files |
| `Symbol` | Load `.sym` files, inspect pins and metadata |
| `SymbolLibrary` | Resolve symbol references from library paths |
| `XschemConfig` | Parse `xschemrc` to extract library paths |
| `XschemCLI` | Wrapper for the xschem binary |
| `HierarchyNode` | Node in the design hierarchy tree |

### Data Model

| Class | Line prefix | Description |
|-|-|-|
| `Component` | `C` | Component instance with symbol, position, attributes |
| `Net` | `N` | Wire segment with endpoints and optional label |
| `Text` | `T` | Text annotation |
| `Header` | `v/G/K/V/S/E` | File header block |
| `Pin` | — | Symbol pin (extracted from layer-5 boxes) |

## Requirements

- Python 3.10+
- No runtime dependencies
- xschem binary required only for `XschemCLI` (netlisting)

## Development

```bash
uv sync --extra dev
uv run pytest
uv run ruff check src/
```

## License

GNU GPLv3
