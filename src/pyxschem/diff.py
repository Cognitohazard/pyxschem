"""Structural diffing of xschem schematics.

Compares two schematics element-by-element and reports added, removed,
and modified components, nets, and texts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from pyxschem.model import Component, Net, Text

if TYPE_CHECKING:
    from pyxschem.schematic import Schematic


@dataclass
class ComponentChange:
    """A single component difference between two schematics."""

    name: str
    kind: Literal["added", "removed", "modified"]
    old: Component | None
    new: Component | None
    changed_attrs: dict[str, tuple[str | None, str | None]] = field(
        default_factory=dict
    )


@dataclass
class NetChange:
    """A net that was added or removed."""

    kind: Literal["added", "removed"]
    net: Net


@dataclass
class TextChange:
    """A text element that was added or removed."""

    kind: Literal["added", "removed"]
    text: Text


@dataclass
class SchemDiff:
    """Result of comparing two schematics."""

    component_changes: list[ComponentChange] = field(default_factory=list)
    net_changes: list[NetChange] = field(default_factory=list)
    text_changes: list[TextChange] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return (
            not self.component_changes
            and not self.net_changes
            and not self.text_changes
        )


def _component_key(c: Component) -> str:
    """Key a component by name, falling back to (symbol, x, y)."""
    if c.name:
        return c.name
    return f"__unnamed__{c.symbol}_{c.x}_{c.y}"


def diff_schematics(old: Schematic, new: Schematic) -> SchemDiff:
    """Compare two schematics and return their structural differences.

    Args:
        old: The baseline schematic.
        new: The updated schematic.

    Returns:
        A SchemDiff describing all changes.
    """
    result = SchemDiff()

    # --- Components ---
    old_comps = {_component_key(c): c for c in old.components}
    new_comps = {_component_key(c): c for c in new.components}

    old_keys = set(old_comps)
    new_keys = set(new_comps)

    for key in sorted(old_keys - new_keys):
        c = old_comps[key]
        result.component_changes.append(
            ComponentChange(name=key, kind="removed", old=c, new=None)
        )

    for key in sorted(new_keys - old_keys):
        c = new_comps[key]
        result.component_changes.append(
            ComponentChange(name=key, kind="added", old=None, new=c)
        )

    for key in sorted(old_keys & new_keys):
        oc = old_comps[key]
        nc = new_comps[key]
        if oc.symbol == nc.symbol and oc.attributes == nc.attributes:
            continue
        changed: dict[str, tuple[str | None, str | None]] = {}
        if oc.symbol != nc.symbol:
            changed["symbol"] = (oc.symbol, nc.symbol)
        all_attr_keys = set(oc.attributes) | set(nc.attributes)
        for ak in sorted(all_attr_keys):
            ov = oc.attributes.get(ak)
            nv = nc.attributes.get(ak)
            if ov != nv:
                changed[ak] = (ov, nv)
        result.component_changes.append(
            ComponentChange(
                name=key, kind="modified", old=oc, new=nc, changed_attrs=changed
            )
        )

    # --- Nets ---
    old_nets = {(n.x1, n.y1, n.x2, n.y2): n for n in old.nets}
    new_nets = {(n.x1, n.y1, n.x2, n.y2): n for n in new.nets}

    for key in sorted(set(old_nets) - set(new_nets)):
        result.net_changes.append(NetChange(kind="removed", net=old_nets[key]))
    for key in sorted(set(new_nets) - set(old_nets)):
        result.net_changes.append(NetChange(kind="added", net=new_nets[key]))

    # --- Texts ---
    old_texts = {t.text: t for t in old.texts}
    new_texts = {t.text: t for t in new.texts}

    for key in sorted(set(old_texts) - set(new_texts)):
        result.text_changes.append(TextChange(kind="removed", text=old_texts[key]))
    for key in sorted(set(new_texts) - set(old_texts)):
        result.text_changes.append(TextChange(kind="added", text=new_texts[key]))

    return result
