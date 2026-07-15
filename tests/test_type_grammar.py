"""Component-level tests for ``zros2.generator._type_grammar``.

Tests the Lark-based ROS 2 type expression parser in isolation — every
``parse_type()`` code path, every array/sequence/string variant, and all
edge cases such as malformed input and unexpected tokens.
"""

import pytest
from lark import LarkError

from zros2.generator._type_grammar import (
    TypeInfo,
    parse_type,
    ROS2_PRIMITIVE_TYPES,
)


# ======================================================================
# ROS2_PRIMITIVE_TYPES
# ======================================================================

class TestROS2PrimitiveTypes:
    """The set of recognised ROS 2 primitive type names."""

    def test_contains_all_primitives(self):
        assert "bool" in ROS2_PRIMITIVE_TYPES
        assert "byte" in ROS2_PRIMITIVE_TYPES
        assert "char" in ROS2_PRIMITIVE_TYPES
        assert "int8" in ROS2_PRIMITIVE_TYPES
        assert "uint8" in ROS2_PRIMITIVE_TYPES
        assert "int16" in ROS2_PRIMITIVE_TYPES
        assert "uint16" in ROS2_PRIMITIVE_TYPES
        assert "int32" in ROS2_PRIMITIVE_TYPES
        assert "uint32" in ROS2_PRIMITIVE_TYPES
        assert "int64" in ROS2_PRIMITIVE_TYPES
        assert "uint64" in ROS2_PRIMITIVE_TYPES
        assert "float32" in ROS2_PRIMITIVE_TYPES
        assert "float64" in ROS2_PRIMITIVE_TYPES
        assert "string" in ROS2_PRIMITIVE_TYPES
        assert "wstring" in ROS2_PRIMITIVE_TYPES

    def test_does_not_contain_nested(self):
        assert "std_msgs/msg/String" not in ROS2_PRIMITIVE_TYPES
        assert "Header" not in ROS2_PRIMITIVE_TYPES
        assert "time" not in ROS2_PRIMITIVE_TYPES
        assert "duration" not in ROS2_PRIMITIVE_TYPES


# ======================================================================
# parse_type() — scalar primitives
# ======================================================================

class TestParseScalarPrimitives:
    """Bare primitive type names (no array suffix, no bounds)."""

    def test_int32(self):
        info = parse_type("int32")
        assert info == TypeInfo(base_name="int32")

    def test_float64(self):
        info = parse_type("float64")
        assert info == TypeInfo(base_name="float64")

    def test_bool(self):
        info = parse_type("bool")
        assert info == TypeInfo(base_name="bool")

    def test_byte(self):
        info = parse_type("byte")
        assert info == TypeInfo(base_name="byte")

    def test_char(self):
        info = parse_type("char")
        assert info == TypeInfo(base_name="char")

    def test_int8(self):
        info = parse_type("int8")
        assert info == TypeInfo(base_name="int8")

    def test_uint64(self):
        info = parse_type("uint64")
        assert info == TypeInfo(base_name="uint64")


# ======================================================================
# parse_type() — string / wstring (unbounded and bounded)
# ======================================================================

class TestParseStringTypes:
    """String and wstring types with and without bounds."""

    def test_string_unbounded(self):
        info = parse_type("string")
        assert info.base_name == "string"
        assert not info.is_bounded_string
        assert info.string_max is None

    def test_string_bounded(self):
        info = parse_type("string<=255")
        assert info.base_name == "string"
        assert info.is_bounded_string
        assert info.string_max == 255

    def test_string_bounded_zero(self):
        info = parse_type("string<=0")
        assert info.is_bounded_string
        assert info.string_max == 0

    def test_wstring_unbounded(self):
        info = parse_type("wstring")
        assert info.base_name == "wstring"
        assert not info.is_bounded_string

    def test_wstring_bounded(self):
        info = parse_type("wstring<=10")
        assert info.base_name == "wstring"
        assert info.is_bounded_string
        assert info.string_max == 10

    def test_bounded_string_multi_digit(self):
        info = parse_type("string<=65535")
        assert info.string_max == 65535


# ======================================================================
# parse_type() — dynamic arrays (unbounded [])
# ======================================================================

class TestParseUnboundedArrays:
    """``type[]`` — unbounded dynamic arrays."""

    def test_int32_array(self):
        info = parse_type("int32[]")
        assert info.base_name == "int32"
        assert info.kind == "unbounded"
        assert info.array_size is None
        assert info.array_max is None

    def test_float64_array(self):
        info = parse_type("float64[]")
        assert info.base_name == "float64"
        assert info.kind == "unbounded"

    def test_bool_array(self):
        info = parse_type("bool[]")
        assert info.base_name == "bool"
        assert info.kind == "unbounded"

    def test_string_array(self):
        info = parse_type("string[]")
        assert info.base_name == "string"
        assert info.kind == "unbounded"


# ======================================================================
# parse_type() — fixed-size arrays [N]
# ======================================================================

class TestParseFixedArrays:
    """``type[N]`` — fixed-size arrays."""

    def test_float64_fixed_3(self):
        info = parse_type("float64[3]")
        assert info.base_name == "float64"
        assert info.kind == "fixed"
        assert info.array_size == 3
        assert info.array_max is None

    def test_uint8_fixed_16(self):
        info = parse_type("uint8[16]")
        assert info.base_name == "uint8"
        assert info.kind == "fixed"
        assert info.array_size == 16

    def test_large_fixed_size(self):
        info = parse_type("int32[1024]")
        assert info.array_size == 1024

    def test_fixed_one_element(self):
        info = parse_type("int32[1]")
        assert info.array_size == 1


# ======================================================================
# parse_type() — bounded dynamic arrays [<=N]
# ======================================================================

class TestParseBoundedArrays:
    """``type[<=N]`` — bounded dynamic arrays."""

    def test_int32_bounded_5(self):
        info = parse_type("int32[<=5]")
        assert info.base_name == "int32"
        assert info.kind == "bounded"
        assert info.array_size is None
        assert info.array_max == 5

    def test_string_bounded_100(self):
        info = parse_type("string[<=100]")
        assert info.base_name == "string"
        assert info.kind == "bounded"
        assert info.array_max == 100


# ======================================================================
# parse_type() — bounded string in bounded array
# ======================================================================

class TestParseBoundedStringInBoundedArray:
    """``string<=M[<=N]`` — compound bounded types."""

    def test_bounded_string_bounded_array(self):
        info = parse_type("string<=10[<=5]")
        assert info.base_name == "string"
        assert info.is_bounded_string
        assert info.string_max == 10
        assert info.kind == "bounded"
        assert info.array_max == 5

    def test_bounded_string_fixed_array(self):
        info = parse_type("string<=255[3]")
        assert info.is_bounded_string
        assert info.string_max == 255
        assert info.kind == "fixed"
        assert info.array_size == 3

    def test_bounded_string_unbounded_array(self):
        info = parse_type("wstring<=20[]")
        assert info.base_name == "wstring"
        assert info.is_bounded_string
        assert info.string_max == 20
        assert info.kind == "unbounded"


# ======================================================================
# parse_type() — sequences
# ======================================================================

class TestParseSequences:
    """``sequence<T>`` and ``sequence<T, N>``."""

    def test_sequence_unbounded(self):
        info = parse_type("sequence<uint8>")
        assert info.base_name == "uint8"
        assert info.kind == "unbounded_sequence"
        assert info.array_max is None

    def test_sequence_bounded(self):
        info = parse_type("sequence<uint8,10>")
        assert info.base_name == "uint8"
        assert info.kind == "bounded_sequence"
        assert info.array_max == 10

    def test_sequence_float64(self):
        info = parse_type("sequence<float64>")
        assert info.base_name == "float64"
        assert info.kind == "unbounded_sequence"

    def test_sequence_nested_type(self):
        info = parse_type("sequence<std_msgs/msg/String>")
        assert info.base_name == "std_msgs/msg/String"
        assert info.kind == "unbounded_sequence"

    def test_sequence_bounded_with_big_limit(self):
        info = parse_type("sequence<int32, 1000>")
        assert info.base_name == "int32"
        assert info.kind == "bounded_sequence"
        assert info.array_max == 1000


# ======================================================================
# parse_type() — nested / qualified identifiers
# ======================================================================

class TestParseNestedTypes:
    """Cross-package type references like ``pkg/Type``."""

    def test_two_part(self):
        info = parse_type("std_msgs/String")
        assert info.base_name == "std_msgs/String"

    def test_three_part(self):
        info = parse_type("geometry_msgs/msg/Point")
        assert info.base_name == "geometry_msgs/msg/Point"

    def test_with_slashes_only(self):
        info = parse_type("my_pkg/msg/MyType")
        assert info.base_name == "my_pkg/msg/MyType"

    def test_nested_with_array(self):
        info = parse_type("std_msgs/msg/String[]")
        assert info.base_name == "std_msgs/msg/String"
        assert info.kind == "unbounded"

    def test_identifier_starting_with_underscore(self):
        info = parse_type("_PrivateType")
        assert info.base_name == "_PrivateType"


# ======================================================================
# parse_type() — edge cases and error handling
# ======================================================================

class TestParseEdgeCases:
    """Unusual but valid inputs, and invalid inputs that must raise."""

    def test_single_word_identifier(self):
        """An unqualified nested-type reference is parsed as an identifier."""
        info = parse_type("Header")
        assert info.base_name == "Header"

    def test_identifier_with_numbers(self):
        info = parse_type("MyType123")
        assert info.base_name == "MyType123"

    def test_empty_string_raises(self):
        with pytest.raises(LarkError):
            parse_type("")

    def test_whitespace_only_raises(self):
        with pytest.raises(LarkError):
            parse_type("   \t  ")

    def test_gibberish_raises(self):
        with pytest.raises(LarkError):
            parse_type("@@invalid@@")

    def test_invalid_array_syntax_raises(self):
        with pytest.raises(LarkError):
            parse_type("int32[abc]")

    def test_partial_array_raises(self):
        with pytest.raises(LarkError):
            parse_type("int32[")

    def test_unclosed_sequence_raises(self):
        with pytest.raises(LarkError):
            parse_type("sequence<uint8")

    def test_bounded_string_without_value_raises(self):
        with pytest.raises(LarkError):
            parse_type("string<=")

    def test_sequence_no_angle(self):
        with pytest.raises(LarkError):
            parse_type("sequence")

    def test_unknown_primitive_is_identifier(self):
        """A word that isn't a known primitive is parsed as an identifier."""
        info = parse_type("SomeRandomWord")
        assert info.base_name == "SomeRandomWord"

    def test_whitespace_around_type_is_ignored(self):
        info = parse_type("  int32  ")
        assert info.base_name == "int32"

    def test_whitespace_around_array_brackets(self):
        info = parse_type("int32 [ 3 ]")
        assert info.base_name == "int32"
        assert info.kind == "fixed"
        assert info.array_size == 3


# ======================================================================
# TypeInfo defaults
# ======================================================================

class TestTypeInfoDefaults:
    """The ``TypeInfo`` dataclass default values."""

    def test_default_is_bounded_string_false(self):
        info = TypeInfo(base_name="int32")
        assert not info.is_bounded_string
        assert info.string_max is None

    def test_default_kind_none(self):
        info = TypeInfo(base_name="int32")
        assert info.kind is None

    def test_default_array_size_none(self):
        info = TypeInfo(base_name="int32")
        assert info.array_size is None

    def test_default_array_max_none(self):
        info = TypeInfo(base_name="int32")
        assert info.array_max is None
