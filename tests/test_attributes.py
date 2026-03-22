"""Tests for xschem attribute parsing and serialization."""

from pyxschem.attributes import parse_attributes, serialize_attributes


class TestParseSimple:
    def test_basic_key_value_pairs(self):
        result = parse_attributes("{name=R1 value=10k m=1}")
        assert result == {"name": "R1", "value": "10k", "m": "1"}

    def test_single_attribute(self):
        result = parse_attributes("{name=R1}")
        assert result == {"name": "R1"}

    def test_empty_block(self):
        result = parse_attributes("{}")
        assert result == {}

    def test_whitespace_only(self):
        result = parse_attributes("{   }")
        assert result == {}

    def test_without_outer_braces(self):
        result = parse_attributes("name=R1 value=10k")
        assert result == {"name": "R1", "value": "10k"}

    def test_preserves_insertion_order(self):
        result = parse_attributes("{name=R1 value=10k m=1}")
        assert list(result.keys()) == ["name", "value", "m"]


class TestParseQuoted:
    def test_double_quoted_value_with_spaces(self):
        result = parse_attributes('{name=V1 value="PWL(0 0 1n 1.8)"}')
        assert result["value"] == "PWL(0 0 1n 1.8)"

    def test_double_quoted_value_with_escaped_quote(self):
        result = parse_attributes(r'{name=V1 value="say \"hello\""}')
        assert result["value"] == 'say "hello"'

    def test_double_quoted_empty(self):
        result = parse_attributes('{name=V1 value=""}')
        assert result["value"] == ""


class TestParseBraced:
    def test_braced_value_with_spaces(self):
        result = parse_attributes(
            "{name=X1 value={sky130_fd_pr__nfet_01v8 W=1 L=0.15}}"
        )
        assert result["value"] == "sky130_fd_pr__nfet_01v8 W=1 L=0.15"

    def test_braced_value_with_nested_braces(self):
        result = parse_attributes("{name=X1 value={outer {inner} end}}")
        assert result["value"] == "outer {inner} end"

    def test_braced_value_with_equals(self):
        result = parse_attributes("{name=X1 value={W=1 L=0.15 nf=2}}")
        assert result["value"] == "W=1 L=0.15 nf=2"

    def test_mixed_simple_and_braced(self):
        result = parse_attributes(
            "{name=R1 value=10k model={sky130_fd_pr__res_generic_m1} m=1}"
        )
        assert result == {
            "name": "R1",
            "value": "10k",
            "model": "sky130_fd_pr__res_generic_m1",
            "m": "1",
        }


class TestParseNewlines:
    def test_newline_separated(self):
        result = parse_attributes("{name=R1\nvalue=10k\nm=1}")
        assert result == {"name": "R1", "value": "10k", "m": "1"}

    def test_mixed_spaces_and_newlines(self):
        result = parse_attributes("{name=R1 value=10k\nm=1}")
        assert result == {"name": "R1", "value": "10k", "m": "1"}

    def test_leading_trailing_whitespace(self):
        result = parse_attributes("{  name=R1  value=10k  }")
        assert result == {"name": "R1", "value": "10k"}


class TestParseEdgeCases:
    def test_value_with_parentheses(self):
        result = parse_attributes("{name=V1 value=DC(1.8)}")
        assert result["value"] == "DC(1.8)"

    def test_multiple_spaces_between_pairs(self):
        result = parse_attributes("{name=R1    value=10k}")
        assert result == {"name": "R1", "value": "10k"}

    def test_tab_separated(self):
        result = parse_attributes("{name=R1\tvalue=10k}")
        assert result == {"name": "R1", "value": "10k"}

    def test_bare_key_no_value(self):
        result = parse_attributes("{spice_ignore}")
        assert result == {"spice_ignore": ""}

    def test_key_with_trailing_equals_no_value(self):
        result = parse_attributes("{name=R1 value=}")
        assert result == {"name": "R1", "value": ""}

    def test_real_world_component(self):
        """Real xschem component attribute block."""
        text = (
            "{name=M1 model=nfet_01v8 w=1 l=0.15 nf=1 mult=1"
            " ad=\"'int((nf+1)/2) * W/nf * 0.29'\""
            " pd=\"'2*int((nf+1)/2) * (W/nf + 0.29)'\"}"
        )
        result = parse_attributes(text)
        assert result["name"] == "M1"
        assert result["model"] == "nfet_01v8"
        assert result["w"] == "1"

    def test_braced_multiline_value(self):
        text = "{name=X1 value={line1\nline2\nline3}}"
        result = parse_attributes(text)
        assert result["value"] == "line1\nline2\nline3"


class TestSerialize:
    def test_simple_values(self):
        result = serialize_attributes({"name": "R1", "value": "10k"})
        assert result == "{name=R1 value=10k}"

    def test_empty_dict(self):
        assert serialize_attributes({}) == "{}"

    def test_value_with_spaces_gets_braced(self):
        result = serialize_attributes({"name": "V1", "value": "PWL(0 0 1n 1.8)"})
        assert result == "{name=V1 value={PWL(0 0 1n 1.8)}}"

    def test_value_with_equals_gets_braced(self):
        result = serialize_attributes({"name": "X1", "value": "W=1 L=0.15"})
        assert result == "{name=X1 value={W=1 L=0.15}}"

    def test_value_with_braces_gets_braced(self):
        result = serialize_attributes({"name": "X1", "value": "outer {inner}"})
        assert result == "{name=X1 value={outer {inner}}}"

    def test_bare_key_no_value(self):
        result = serialize_attributes({"spice_ignore": ""})
        assert result == "{spice_ignore}"

    def test_preserves_order(self):
        result = serialize_attributes({"name": "R1", "value": "10k", "m": "1"})
        assert result == "{name=R1 value=10k m=1}"


class TestRoundTrip:
    def test_simple_round_trip(self):
        original = {"name": "R1", "value": "10k", "m": "1"}
        assert parse_attributes(serialize_attributes(original)) == original

    def test_quoted_round_trip(self):
        original = {"name": "V1", "value": "PWL(0 0 1n 1.8)"}
        assert parse_attributes(serialize_attributes(original)) == original

    def test_complex_round_trip(self):
        original = {"name": "X1", "value": "sky130 W=1 L=0.15", "m": "2"}
        assert parse_attributes(serialize_attributes(original)) == original

    def test_parse_serialize_preserves_semantics(self):
        text = "{name=R1 value=10k m=1}"
        result = serialize_attributes(parse_attributes(text))
        assert parse_attributes(result) == parse_attributes(text)

    def test_braced_value_round_trip(self):
        original = {"name": "X1", "value": "outer {inner} end"}
        assert parse_attributes(serialize_attributes(original)) == original
