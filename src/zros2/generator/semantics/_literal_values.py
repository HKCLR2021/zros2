"""Parse ROS 2 interface literals and scalar defaults into Python values.

This module deliberately does not import :mod:`ast` and does not build code:
literal semantics belong here, AST construction belongs to codegen.
"""

from zros2.generator.parsing._types import TypeInfo

from ._native_types import FLOAT_TYPES, INT_TYPES, STRING_TYPES


def unquote(raw: str) -> str:
    """Return a ROS string literal, accepting optional surrounding quotes."""
    text = raw.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ('"', "'"):
        inner = text[1:-1]
        return (
            inner.replace('\\"', '"')
            .replace("\\'", "'")
            .replace("\\\\", "\\")
        )
    return text


def parse_literal(raw: str, info: TypeInfo, context: str) -> object:
    """Parse a ROS ``.msg`` constant/default value into a Python literal."""
    base = info.base_name
    text = raw.strip()

    if info.is_bounded_string or base in STRING_TYPES:
        return unquote(text)
    if base == "bool":
        lowered = text.lower()
        if lowered in ("true", "1"):
            return True
        if lowered in ("false", "0"):
            return False
        raise ValueError(f"{context}: invalid bool value {raw!r}")
    if base in INT_TYPES:
        try:
            return int(text, 0)
        except ValueError as error:
            raise ValueError(f"{context}: invalid integer value {raw!r}") from error
    if base in FLOAT_TYPES:
        lowered = text.lower()
        if lowered in ("nan", "+nan", "-nan"):
            return float("nan")
        if lowered in ("inf", "+inf", "infinity", "+infinity"):
            return float("inf")
        if lowered in ("-inf", "-infinity"):
            return float("-inf")
        try:
            return float(text)
        except ValueError as error:
            raise ValueError(f"{context}: invalid float value {raw!r}") from error
    raise ValueError(
        f"{context}: default/value expressions are not supported for {base!r}"
    )


def default_scalar(info: TypeInfo) -> object:
    """Return the zero/empty default for a scalar field."""
    base = info.base_name
    if info.is_bounded_string or base in STRING_TYPES:
        return ""
    if base == "bool":
        return False
    if base in INT_TYPES:
        return 0
    if base in FLOAT_TYPES:
        return 0.0
    raise ValueError(f"Unsupported scalar type {base!r}")


__all__ = ["default_scalar", "parse_literal", "unquote"]
