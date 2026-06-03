"""Property-based tests (hypothesis) for codecs and formatting.

These exercise round-trip and value-preservation invariants over
generated inputs.  Strategies are deliberately scoped to what xschem
actually accepts and to the documented guarantees of each function.
"""

from __future__ import annotations

import math

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from pyxschem.attributes import parse_attributes, serialize_attributes
from pyxschem.model import Component, Net, _fmt_num
from pyxschem.parser import parse_schematic

# ---------------------------------------------------------------------------
# Deterministic, reproducible CI profile.
# ---------------------------------------------------------------------------

settings.register_profile(
    "ci",
    settings(
        max_examples=200,
        derandomize=True,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    ),
)
settings.load_profile("ci")


# ---------------------------------------------------------------------------
# Strategies — scoped to what xschem attribute blocks actually allow.
# ---------------------------------------------------------------------------

# Keys: non-empty, alphanumeric/underscore only (no '=', whitespace, braces).
_attr_keys = st.text(
    alphabet=st.characters(
        whitelist_categories=("Lu", "Ll", "Nd"),
        whitelist_characters="_",
    ),
    min_size=1,
    max_size=12,
)

# Values (conservative): text without control chars and without braces, so
# braces are trivially balanced.  This is the minimal domain the codec must
# handle; richer balanced-brace values are covered manually in the suite.
_attr_values = st.text(
    alphabet=st.characters(
        blacklist_categories=("Cc", "Cs"),
        blacklist_characters="{}",
    ),
    max_size=24,
)

_attr_dicts = st.dictionaries(_attr_keys, _attr_values, max_size=6)


# ---------------------------------------------------------------------------
# Attribute codec round-trip.
# ---------------------------------------------------------------------------


class TestAttributeCodecRoundTrip:
    @given(_attr_dicts)
    def test_parse_inverts_serialize(self, attrs):
        assert parse_attributes(serialize_attributes(attrs)) == attrs

    @given(_attr_keys, _attr_values)
    def test_single_pair_round_trip(self, key, value):
        d = {key: value}
        assert parse_attributes(serialize_attributes(d)) == d


# ---------------------------------------------------------------------------
# Float formatting (_fmt_num).
# ---------------------------------------------------------------------------


class TestFmtNum:
    @given(st.integers(min_value=-(10**12), max_value=10**12))
    def test_integral_floats_have_no_decimal_point(self, i):
        # Any whole-number float renders as a bare integer (no '.' or 'e').
        s = _fmt_num(float(i))
        assert s == str(i)
        assert "." not in s

    def test_known_integral_examples(self):
        assert _fmt_num(300.0) == "300"
        assert _fmt_num(-7.0) == "-7"
        assert _fmt_num(0.0) == "0"

    @given(
        st.floats(
            allow_nan=False,
            allow_infinity=False,
            min_value=-1e9,
            max_value=1e9,
        )
    )
    def test_value_preserving_within_precision_domain(self, v):
        # _fmt_num uses ".10g" (10 significant digits).  Within a domain that
        # round-trips at 10 sig-figs, the formatted text parses back exactly.
        # We snap the generated float to its own 10g rendering first so the
        # property is about formatter stability, not about >10-digit inputs
        # (which the formatter intentionally truncates — see module docstring).
        v10 = float(format(v, ".10g"))
        assert math.isfinite(v10)
        assert float(_fmt_num(v10)) == v10


# ---------------------------------------------------------------------------
# Structural dataclass round-trip via to_line() / parse_schematic().
# ---------------------------------------------------------------------------

# Coordinates restricted to values _fmt_num renders losslessly: integers and
# half-integers stay within the .10g precision window.
_coords = st.one_of(
    st.integers(min_value=-100000, max_value=100000).map(float),
    st.integers(min_value=-100000, max_value=100000).map(lambda i: i + 0.5),
)


class TestStructuralRoundTrip:
    @given(_coords, _coords, _coords, _coords, _attr_dicts)
    def test_net_round_trips(self, x1, y1, x2, y2, attrs):
        net = Net(x1=x1, y1=y1, x2=x2, y2=y2, attributes=dict(attrs), raw_line=None)
        reparsed = parse_schematic(net.to_line() + "\n")[0]
        assert isinstance(reparsed, Net)
        assert (reparsed.x1, reparsed.y1, reparsed.x2, reparsed.y2) == (x1, y1, x2, y2)
        assert dict(reparsed.attributes) == attrs

    @given(
        _coords,
        _coords,
        st.integers(min_value=0, max_value=3),
        st.integers(min_value=0, max_value=1),
        _attr_dicts,
    )
    def test_component_round_trips(self, x, y, rotation, mirror, attrs):
        comp = Component(
            symbol="res.sym",
            x=x,
            y=y,
            rotation=rotation,
            mirror=mirror,
            attributes=dict(attrs),
            raw_line=None,
        )
        reparsed = parse_schematic(comp.to_line() + "\n")[0]
        assert isinstance(reparsed, Component)
        assert reparsed.symbol == "res.sym"
        assert (reparsed.x, reparsed.y) == (x, y)
        assert reparsed.rotation == rotation
        assert reparsed.mirror == mirror
        assert dict(reparsed.attributes) == attrs
