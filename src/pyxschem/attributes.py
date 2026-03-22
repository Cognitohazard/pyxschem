"""Parse and serialize xschem Tcl-style attribute blocks.

xschem attribute blocks use Tcl-like quoting rules:
  {name=R1 value=10k m=1}              — simple key=value
  {name=V1 value="PWL(0 0 1n 1.8)"}   — double-quoted values
  {name=X1 value={nfet W=1 L=0.15}}   — brace-quoted values (braces nest)
"""

from __future__ import annotations


def parse_attributes(text: str) -> dict[str, str]:
    """Parse an xschem attribute block string into a dict.

    Args:
        text: Attribute block, with or without outer braces.
              e.g. "{name=R1 value=10k}" or "name=R1 value=10k"

    Returns:
        Ordered dict of key=value pairs.
    """
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        text = text[1:-1]
    if not text.strip():
        return {}

    result: dict[str, str] = {}
    i = 0
    n = len(text)

    while i < n:
        # Skip whitespace (spaces, tabs, newlines)
        while i < n and text[i] in " \t\n\r":
            i += 1
        if i >= n:
            break

        # Parse key (everything up to '=' or whitespace)
        key_start = i
        while i < n and text[i] not in "= \t\n\r":
            i += 1

        key = text[key_start:i]
        if not key:
            break

        # Skip whitespace between key and '='
        while i < n and text[i] in " \t":
            i += 1

        # Check for '='
        if i >= n or text[i] != "=":
            # Bare key with no value
            result[key] = ""
            continue

        i += 1  # skip '='

        # Parse value
        if i >= n:
            result[key] = ""
            continue

        if text[i] == '"':
            # Double-quoted value
            i += 1  # skip opening quote
            value_chars: list[str] = []
            while i < n and text[i] != '"':
                if text[i] == "\\" and i + 1 < n:
                    next_char = text[i + 1]
                    if next_char == '"':
                        value_chars.append('"')
                        i += 2
                        continue
                    elif next_char == "\\":
                        value_chars.append("\\")
                        i += 2
                        continue
                value_chars.append(text[i])
                i += 1
            if i < n:
                i += 1  # skip closing quote
            result[key] = "".join(value_chars)

        elif text[i] == "{":
            # Brace-quoted value — track nesting depth
            i += 1  # skip opening brace
            depth = 1
            value_start = i
            while i < n and depth > 0:
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                i += 1
            # i is now past the closing brace
            result[key] = text[value_start : i - 1]

        else:
            # Unquoted value — ends at whitespace
            value_start = i
            while i < n and text[i] not in " \t\n\r":
                i += 1
            result[key] = text[value_start:i]

    return result


def serialize_attributes(attrs: dict[str, str]) -> str:
    """Serialize an attributes dict to xschem format.

    Args:
        attrs: Dict of key=value pairs.

    Returns:
        Attribute block string including outer braces, e.g. "{name=R1 value=10k}"
    """
    if not attrs:
        return "{}"

    pairs: list[str] = []
    for key, value in attrs.items():
        if not value:
            pairs.append(key)
        elif _needs_quoting(value):
            pairs.append(f"{key}={{{value}}}")
        else:
            pairs.append(f"{key}={value}")

    return "{" + " ".join(pairs) + "}"


def _needs_quoting(value: str) -> bool:
    """Check if a value needs brace quoting."""
    return any(ch in ' \t\n\r{}"=' for ch in value)
