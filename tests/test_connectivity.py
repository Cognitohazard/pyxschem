"""Tests for pyxschem.connectivity."""

from __future__ import annotations

from conftest import make_symbol, mock_libs

from pyxschem.connectivity import (
    _parse_spice_netlist,
    connectivity_from_schematic,
)
from pyxschem.schematic import Schematic
from pyxschem.symbol import Pin, Symbol

# ---------------------------------------------------------------------------
# SPICE netlist parsing
# ---------------------------------------------------------------------------


class TestParseSpiceNetlist:
    def test_resistor(self):
        text = "R1 net1 net2 1k\n"
        result = _parse_spice_netlist(text)
        names = {nc.net_name for nc in result}
        assert "net1" in names
        assert "net2" in names
        # R1.p on net1, R1.m on net2
        net1 = next(nc for nc in result if nc.net_name == "net1")
        assert ("R1", "p") in net1.pins

    def test_mosfet(self):
        text = "M1 drain gate source bulk nmos_model w=1u l=0.5u\n"
        result = _parse_spice_netlist(text)
        drain_net = next(nc for nc in result if nc.net_name == "drain")
        assert ("M1", "d") in drain_net.pins

    def test_subcircuit(self):
        text = (
            ".subckt inv in out vdd vss\n"
            "M1 out in vdd vdd pmos\n"
            "M2 out in vss vss nmos\n"
            ".ends inv\n"
            "\n"
            "X1 a b VDD GND inv\n"
        )
        result = _parse_spice_netlist(text)
        a_net = next(nc for nc in result if nc.net_name == "a")
        assert ("X1", "in") in a_net.pins

    def test_voltage_source(self):
        text = "V1 vdd 0 1.8\n"
        result = _parse_spice_netlist(text)
        vdd_net = next(nc for nc in result if nc.net_name == "vdd")
        assert ("V1", "p") in vdd_net.pins

    def test_comments_ignored(self):
        text = "* This is a comment\nR1 a b 1k\n"
        result = _parse_spice_netlist(text)
        assert len(result) == 2  # a and b

    def test_continuation_lines(self):
        text = "M1 drain gate\n+ source bulk nmos w=1u l=0.5u\n"
        result = _parse_spice_netlist(text)
        assert any(nc.net_name == "drain" for nc in result)

    def test_empty(self):
        assert _parse_spice_netlist("") == []
        assert _parse_spice_netlist("* comment only\n") == []


# ---------------------------------------------------------------------------
# Pure Python connectivity
# ---------------------------------------------------------------------------


class TestConnectivityFromSchematic:
    def test_simple_net_label_connection(self):
        """Two components sharing the same net label are connected."""
        sym = make_symbol(
            -5,
            -5,
            5,
            5,
            pins=[
                Pin(name="P", direction="inout", x=0, y=-20),
                Pin(name="N", direction="inout", x=0, y=20),
            ],
        )
        libs = mock_libs(("res.sym", sym))

        sch = Schematic.new()
        sch.add_component("res.sym", x=0, y=0, attributes={"name": "R1"})
        sch.add_component("res.sym", x=100, y=0, attributes={"name": "R2"})

        # R1.P at (0, -20) connected to VDD label
        sch.add_net(0, -20, 0, -20, label="VDD")
        # R2.P at (100, -20) connected to VDD label
        sch.add_net(100, -20, 100, -20, label="VDD")

        result = connectivity_from_schematic(sch, libs)
        vdd = next(nc for nc in result if nc.net_name == "VDD")
        comp_names = {p[0] for p in vdd.pins}
        assert "R1" in comp_names
        assert "R2" in comp_names

    def test_endpoint_sharing(self):
        """Two nets sharing an endpoint position are on the same net."""
        sym = make_symbol(
            -5,
            -5,
            5,
            5,
            pins=[
                Pin(name="P", direction="inout", x=0, y=0),
            ],
        )
        libs = mock_libs(("res.sym", sym))

        sch = Schematic.new()
        sch.add_component("res.sym", x=0, y=0, attributes={"name": "R1"})
        sch.add_component("res.sym", x=100, y=0, attributes={"name": "R2"})

        # Wire from R1.P to R2.P
        sch.add_net(0, 0, 50, 0)
        sch.add_net(50, 0, 100, 0)

        result = connectivity_from_schematic(sch, libs)
        # Both pins should be on the same net
        for nc in result:
            r1 = any(p[0] == "R1" for p in nc.pins)
            r2 = any(p[0] == "R2" for p in nc.pins)
            if r1 and r2:
                break
        else:
            raise AssertionError("R1 and R2 should be on the same net")

    def test_disconnected_components(self):
        """Components with no shared nets or labels are separate."""
        sym = make_symbol(
            -5,
            -5,
            5,
            5,
            pins=[
                Pin(name="P", direction="inout", x=0, y=0),
            ],
        )
        libs = mock_libs(("res.sym", sym))

        sch = Schematic.new()
        sch.add_component("res.sym", x=0, y=0, attributes={"name": "R1"})
        sch.add_component("res.sym", x=100, y=0, attributes={"name": "R2"})

        sch.add_net(0, 0, 0, 0, label="A")
        sch.add_net(100, 0, 100, 0, label="B")

        result = connectivity_from_schematic(sch, libs)
        assert len(result) == 2

    def test_auto_naming_for_unlabeled(self):
        """Unlabeled nets get auto-generated names."""
        sym = make_symbol(
            -5,
            -5,
            5,
            5,
            pins=[
                Pin(name="P", direction="inout", x=0, y=0),
            ],
        )
        libs = mock_libs(("res.sym", sym))

        sch = Schematic.new()
        sch.add_component("res.sym", x=0, y=0, attributes={"name": "R1"})
        sch.add_net(0, 0, 50, 0)  # no label

        result = connectivity_from_schematic(sch, libs)
        assert any(nc.net_name.startswith("net_") for nc in result)

    def test_empty_schematic(self):
        libs = mock_libs()
        sch = Schematic.new()
        result = connectivity_from_schematic(sch, libs)
        assert result == []


# ---------------------------------------------------------------------------
# Net-name adoption from label/port symbols.
# ---------------------------------------------------------------------------


def _label_symbol() -> Symbol:
    return Symbol.from_text(
        "v {xschem version=3.4.5 file_version=1.2}\n"
        "G {}\n"
        "K {type=label net_name=true format=\"*.alias @lab\" "
        "template=\"name=p1 lab=xxx\"}\n"
        "V {}\nS {}\nE {}\n"
        "B 5 -2.5 -2.5 2.5 2.5 {name=p dir=in}\n"
    )


class TestNetNameFromLabelSymbol:
    def test_label_pin_propagates_lab_attribute(self):
        res = make_symbol(-10, -10, 10, 10)
        res.add_pin("P", "in", 0, 0)
        libs = mock_libs(("res.sym", res), ("lab_pin.sym", _label_symbol()))
        sch = Schematic.new()
        sch.add_component("res.sym", 100, -100, attributes={"name": "R1"})
        sch.add_component("lab_pin.sym", 100, -100,
                           attributes={"name": "lp_1", "lab": "VDD"})
        nets = connectivity_from_schematic(sch, libs)
        names = {n.net_name for n in nets}
        assert "VDD" in names

    def test_unrelated_lab_attribute_ignored(self):
        # A regular component with `lab=...` is NOT a label-type symbol;
        # its lab must not be adopted as the net name.
        res = make_symbol(-10, -10, 10, 10)
        res.add_pin("P", "in", 0, 0)
        libs = mock_libs(("res.sym", res))
        sch = Schematic.new()
        sch.add_component("res.sym", 100, -100,
                           attributes={"name": "R1", "lab": "FAKE"})
        nets = connectivity_from_schematic(sch, libs)
        names = {n.net_name for n in nets}
        assert "FAKE" not in names

    def test_port_type_symbol_also_propagates(self):
        # type="port" (ipin/opin idiom) is recognised the same way.
        port = Symbol.from_text(
            "v {xschem version=3.4.5 file_version=1.2}\n"
            "G {}\n"
            "K {type=port net_name=true format=\"*.ipin @lab\" "
            "template=\"name=p1 lab=xxx\"}\n"
            "V {}\nS {}\nE {}\n"
            "B 5 -2.5 -2.5 2.5 2.5 {name=p dir=in}\n"
        )
        res = make_symbol(-10, -10, 10, 10)
        res.add_pin("P", "in", 0, 0)
        libs = mock_libs(("res.sym", res), ("ipin.sym", port))
        sch = Schematic.new()
        sch.add_component("res.sym", 0, 0, attributes={"name": "R1"})
        sch.add_component("ipin.sym", 0, 0,
                           attributes={"name": "p1", "lab": "INPUT"})
        nets = connectivity_from_schematic(sch, libs)
        assert "INPUT" in {n.net_name for n in nets}
