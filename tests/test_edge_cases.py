"""Edge-case tests for bugs found by systematic probing of pure functions."""

from pyxschem.attributes import parse_attributes, serialize_attributes
from pyxschem.model import Text, _fmt_num
from pyxschem.parser import _brace_depth, _split_logical_lines

# ---------------------------------------------------------------------------
# Bug 1: _fmt_num crashes on non-finite floats
# model.py:79 — int(v) raises OverflowError for inf, ValueError for nan
# ---------------------------------------------------------------------------


class TestFmtNumNonFinite:
    def test_positive_infinity(self):
        result = _fmt_num(float("inf"))
        assert result == "inf"

    def test_negative_infinity(self):
        result = _fmt_num(float("-inf"))
        assert result == "-inf"

    def test_nan(self):
        result = _fmt_num(float("nan"))
        assert result == "nan"


# ---------------------------------------------------------------------------
# Bug 2: Text.to_line() doesn't use _fmt_num for xscale / yscale
# model.py:224 — f"{self.xscale}" produces "1.0" instead of "1"
# ---------------------------------------------------------------------------


class TestTextScaleFormatting:
    def test_integer_xscale_yscale_omit_decimal(self):
        """xscale=1.0 and yscale=1.0 should serialize as '1' not '1.0'."""
        t = Text(
            text="Hello",
            x=100,
            y=200,
            rotation=0,
            mirror=0,
            xscale=1.0,
            yscale=1.0,
        )
        line = t.to_line()
        assert line == "T {Hello} 100 200 0 0 1 1 {}"

    def test_fractional_xscale_yscale_preserved(self):
        """Non-integer scales should keep their fractional part."""
        t = Text(
            text="Hello",
            x=0,
            y=0,
            rotation=0,
            mirror=0,
            xscale=0.4,
            yscale=0.3,
        )
        line = t.to_line()
        assert "0.4" in line
        assert "0.3" in line


# ---------------------------------------------------------------------------
# Bug 3: serialize_attributes breaks roundtrip for values with unbalanced }
# attributes.py:127 — brace-quoting doesn't work for unbalanced braces
# ---------------------------------------------------------------------------


class TestSerializeAttributesUnbalancedBraces:
    def test_roundtrip_value_with_closing_brace(self):
        """A value containing '}' must survive serialize -> parse roundtrip."""
        original = {"key": "a}b"}
        assert parse_attributes(serialize_attributes(original)) == original

    def test_roundtrip_value_is_single_closing_brace(self):
        """A value that is just '}' must roundtrip correctly."""
        original = {"val": "}"}
        assert parse_attributes(serialize_attributes(original)) == original

    def test_roundtrip_value_with_opening_brace_only(self):
        """A value with only '{' (no matching '}') must roundtrip."""
        original = {"val": "{"}
        assert parse_attributes(serialize_attributes(original)) == original

    def test_roundtrip_value_with_multiple_unbalanced(self):
        """Values like 'a}}b' or '{{{' must roundtrip."""
        for value in ["a}}b", "{{{", "}}}", "}{", "a{b}c}d"]:
            original = {"k": value}
            result = parse_attributes(serialize_attributes(original))
            assert result == original, f"Roundtrip failed for value={value!r}"


# ---------------------------------------------------------------------------
# Bug 4: _brace_depth doesn't handle backslash-escaped quotes
# parser.py:156 — \" is not recognized, corrupting quote-tracking state
# ---------------------------------------------------------------------------


class TestBraceDepthEscapedQuotes:
    def test_escaped_quote_in_middle_of_value(self):
        r"""Escaped quotes in middle of value must not affect brace tracking.

        Line: {key="a\"b"}
        Correct: depth=0, in_quote=False (\" is escaped, not a real close)
        Buggy:   depth=1, in_quote=True  (\" toggles quote state wrongly)
        """
        line = '{key="a\\"b"}'
        depth, in_quote = _brace_depth(line, False)
        assert depth == 0
        assert in_quote is False


class TestSplitLogicalLinesEscapedQuotes:
    def test_escaped_quote_doesnt_eat_next_element(self):
        r"""Multiline attribute with escaped quote must not swallow next line.

        Input (3 raw lines):
          C {sym} 0 0 0 0 {name=M1
          value="a\"b"}
          N 0 0 100 0 {}

        Expected: 2 logical lines (joined component + separate net).
        Buggy:    1 logical line (net swallowed into component block).
        """
        text = 'C {sym} 0 0 0 0 {name=M1\nvalue="a\\"b"}\nN 0 0 100 0 {}'
        lines = _split_logical_lines(text)
        assert len(lines) == 2
        assert lines[0] == 'C {sym} 0 0 0 0 {name=M1\nvalue="a\\"b"}'
        assert lines[1] == "N 0 0 100 0 {}"
