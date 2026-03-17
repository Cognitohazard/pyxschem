# pyxschem

> **WIP** — This project is under active development. APIs may change without notice. Not yet recommended for production use.

Python library for reading, editing, and generating [xschem](https://xschem.sourceforge.io/) schematic (`.sch`) and symbol (`.sym`) files. Pure Python, zero runtime dependencies, round-trip faithful.

## Installation

```
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
sch.add_component("devices/cap.sym", x=400, y=-200,
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

Compute pin positions in schematic coordinates (handles mirror, rotation, translation) and connect pins to labeled nets.

```python
x, y = sch.pin_position("R1", "P", libs)

sch.connect("M1", "g", "clk", libs)   # label M1's gate pin as "clk"
sch.connect("M1", "d", "VDD", libs)
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

# Generate netlist
netlist = cli.netlist("amp.sch", format="spice", output_dir="build/")
netlist = cli.netlist("top.sch", format="verilog")

# Execute Tcl commands
output = cli.command("puts [xschem get instances]", schematic="amp.sch")
```

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
