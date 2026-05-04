"""Net connectivity analysis for xschem schematics.

Provides:
- ``NetAnalyzer`` — query object for connectivity analysis
- ``connectivity_from_netlist`` — parse SPICE netlist (requires xschem)
- ``connectivity_from_schematic`` — pure Python fallback
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from pyxschem.geometry import transform_point

if TYPE_CHECKING:
    from pyxschem.cli import XschemCLI
    from pyxschem.library import SymbolLibrary
    from pyxschem.schematic import Schematic


@dataclass
class NetConnection:
    """A single electrical net and the component pins connected to it."""

    net_name: str
    pins: list[tuple[str, str]] = field(default_factory=list)
    """List of (component_name, pin_name) tuples."""


def connectivity_from_netlist(path: str | Path) -> list[NetConnection]:
    """Parse a SPICE netlist to extract net-to-pin connectivity.

    Handles the common xschem SPICE netlist format with .subckt
    blocks and component instance lines (R, C, L, M, X, etc.).

    Args:
        path: Path to .spice/.net netlist file.

    Returns:
        List of NetConnection with unique net names.
    """
    text = Path(path).read_text(encoding="utf-8")
    return _parse_spice_netlist(text)


def _parse_spice_netlist(text: str) -> list[NetConnection]:
    """Parse SPICE netlist text into NetConnections."""
    net_pins: dict[str, list[tuple[str, str]]] = {}

    # Track subcircuit port orders from .subckt lines
    subckt_ports: dict[str, list[str]] = {}

    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1

        # Skip comments and directives (except .subckt)
        if not line or line.startswith("*"):
            continue

        # Handle continuation lines (+ prefix)
        while i < len(lines) and lines[i].startswith("+"):
            line += " " + lines[i][1:].strip()
            i += 1

        # .subckt definition — learn port names
        if line.lower().startswith(".subckt"):
            parts = line.split()
            if len(parts) >= 3:
                subckt_name = parts[1]
                # Ports are listed after name, until we hit a param
                ports = []
                for p in parts[2:]:
                    if "=" in p:
                        break
                    ports.append(p)
                subckt_ports[subckt_name] = ports
            continue

        if line.startswith("."):
            continue

        # Instance lines: prefix determines pin count
        prefix = line[0].upper()
        parts = line.split()
        if len(parts) < 3:
            continue

        inst_name = parts[0]

        if prefix in ("R", "C", "L", "D"):
            # 2-terminal: name net1 net2 value [params]
            if len(parts) >= 4:
                nets = parts[1:3]
                pin_names = ["p", "m"] if prefix in ("R", "C", "L") else ["p", "n"]
            else:
                continue
        elif prefix == "Q":
            # BJT: name c b e [s] model
            if len(parts) >= 5:
                nets = parts[1:4]
                pin_names = ["c", "b", "e"]
            else:
                continue
        elif prefix == "M":
            # MOSFET: name d g s b model [params]
            if len(parts) >= 6:
                nets = parts[1:5]
                pin_names = ["d", "g", "s", "b"]
            else:
                continue
        elif prefix == "X":
            # Subcircuit: name net1 net2 ... netN subckt [params]
            # Find the subckt name (last non-param token)
            net_tokens = []
            subckt = None
            for p in parts[1:]:
                if "=" in p:
                    break
                net_tokens.append(p)
            if net_tokens:
                subckt = net_tokens[-1]
                nets = net_tokens[:-1]
                pin_names = subckt_ports.get(subckt, [])
                if len(pin_names) != len(nets):
                    # Fallback: use positional names
                    pin_names = [f"pin{k}" for k in range(len(nets))]
            else:
                continue
        elif prefix == "V" or prefix == "I":
            # Voltage/current source: name p m value
            if len(parts) >= 4:
                nets = parts[1:3]
                pin_names = ["p", "m"]
            else:
                continue
        else:
            continue

        for net_name, pin_name in zip(nets, pin_names, strict=False):
            if net_name not in net_pins:
                net_pins[net_name] = []
            net_pins[net_name].append((inst_name, pin_name))

    return [
        NetConnection(net_name=name, pins=pins)
        for name, pins in sorted(net_pins.items())
    ]


class _UnionFind:
    """Simple union-find for grouping connected positions."""

    def __init__(self) -> None:
        self._parent: dict[int, int] = {}
        self._rank: dict[int, int] = {}

    def make_set(self, x: int) -> None:
        if x not in self._parent:
            self._parent[x] = x
            self._rank[x] = 0

    def find(self, x: int) -> int:
        while self._parent[x] != x:
            self._parent[x] = self._parent[self._parent[x]]
            x = self._parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self._rank[ra] < self._rank[rb]:
            ra, rb = rb, ra
        self._parent[rb] = ra
        if self._rank[ra] == self._rank[rb]:
            self._rank[ra] += 1


def connectivity_from_schematic(
    sch: Schematic, libs: SymbolLibrary
) -> list[NetConnection]:
    """Build connectivity from schematic geometry (pure Python).

    Groups pins and net segments by shared endpoint position,
    then merges groups that share a net label.

    Args:
        sch: The schematic to analyze.
        libs: Symbol library for resolving component symbols.

    Returns:
        List of NetConnection with net names derived from labels
        or auto-generated.
    """
    uf = _UnionFind()

    # Map position → point ID
    pos_to_id: dict[tuple[float, float], int] = {}
    next_id = 0

    def get_id(x: float, y: float) -> int:
        nonlocal next_id
        key = (x, y)
        if key not in pos_to_id:
            pos_to_id[key] = next_id
            uf.make_set(next_id)
            next_id += 1
        return pos_to_id[key]

    # Process net segments — union their endpoints
    label_at: dict[int, str] = {}  # point_id → net label
    for net in sch.nets:
        id1 = get_id(net.x1, net.y1)
        id2 = get_id(net.x2, net.y2)
        uf.union(id1, id2)
        if net.label:
            label_at[id1] = net.label
            label_at[id2] = net.label

    # Register pin positions; for label/port symbols (gnd/vdd/lab_pin/
    # ipin/opin) also adopt their `lab` attribute as the net name.
    pin_at: dict[int, list[tuple[str, str]]] = {}  # point_id → [(comp, pin)]
    for comp in sch.components:
        sym = libs.resolve(comp.symbol)
        if sym is None:
            continue
        comp_label = comp.label
        is_label_symbol = (sym.type or "").lower() in {"label", "port"}
        net_label = comp.attributes.get("lab") if is_label_symbol else None
        for pin in sym.pins:
            px, py = transform_point(
                pin.x, pin.y, comp.x, comp.y, comp.rotation, comp.mirror
            )
            pid = get_id(px, py)
            if pid not in pin_at:
                pin_at[pid] = []
            pin_at[pid].append((comp_label, pin.name))
            if net_label:
                label_at[pid] = net_label

    # Merge groups that share a label
    label_root: dict[str, int] = {}
    for pid, label in label_at.items():
        root = uf.find(pid)
        if label in label_root:
            uf.union(label_root[label], root)
        else:
            label_root[label] = root

    # Collect groups
    groups: dict[int, list[tuple[str, str]]] = {}
    group_labels: dict[int, str] = {}

    for pid, pins in pin_at.items():
        root = uf.find(pid)
        if root not in groups:
            groups[root] = []
        groups[root].extend(pins)

    # Assign labels to groups
    for pid, label in label_at.items():
        root = uf.find(pid)
        group_labels[root] = label

    # Build result
    auto_idx = 0
    result: list[NetConnection] = []
    for root, pins in sorted(groups.items()):
        name = group_labels.get(root)
        if name is None:
            name = f"net_{auto_idx}"
            auto_idx += 1
        # Deduplicate pins
        seen: set[tuple[str, str]] = set()
        unique_pins: list[tuple[str, str]] = []
        for p in pins:
            if p not in seen:
                seen.add(p)
                unique_pins.append(p)
        result.append(NetConnection(net_name=name, pins=unique_pins))

    return result


class NetAnalyzer:
    """Net connectivity analyzer for a schematic.

    Uses xschem's netlist output when a CLI is provided and the
    schematic has a file path.  Falls back to pure-Python endpoint
    matching otherwise.

    Usage::

        na = NetAnalyzer(schematic, libs)
        for net in na.nets():
            print(net.net_name, net.pins)
    """

    def __init__(
        self,
        schematic: Schematic,
        libs: SymbolLibrary,
        cli: XschemCLI | None = None,
    ) -> None:
        self._sch = schematic
        self._libs = libs
        self._cli = cli
        self._nets: list[NetConnection] | None = None
        self._pin_index: dict[tuple[str, str], NetConnection] | None = None

    def nets(self) -> list[NetConnection]:
        """All electrical nets with their connected pins."""
        if self._nets is not None:
            return self._nets

        if self._cli is not None and self._sch.path is not None:
            netlist_path = self._cli.netlist(self._sch.path)
            if netlist_path.exists():
                self._nets = connectivity_from_netlist(netlist_path)
                return self._nets

        self._nets = connectivity_from_schematic(self._sch, self._libs)
        return self._nets

    def net_for_pin(self, comp_name: str, pin_name: str) -> NetConnection | None:
        """Find the net a specific component pin is on (O(1) lookup)."""
        if self._pin_index is None:
            self._pin_index = {}
            for net in self.nets():
                for pin in net.pins:
                    self._pin_index[pin] = net
        return self._pin_index.get((comp_name, pin_name))

    def connected_pins(self, comp_name: str, pin_name: str) -> list[tuple[str, str]]:
        """List all other pins on the same net as the given pin."""
        net = self.net_for_pin(comp_name, pin_name)
        if net is None:
            return []
        return [(c, p) for c, p in net.pins if (c, p) != (comp_name, pin_name)]
