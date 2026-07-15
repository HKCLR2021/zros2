"""Component-level tests for ``zros2.generator._type_map``.

Tests the type resolution layer that maps ROS 2 type expressions to pycdr2
annotation expressions.  Covers every primitive, container, and nested-type
code path, including edge cases for bounded strings, sequences, arrays,
external imports, and the ``root_package`` prefix logic.
"""
from dataclasses import dataclass

from lark import LarkError

from zros2.generator._type_map import (
    ResolvedType,
    resolve_type,
    is_primitive,
    get_default_value,
)


# ======================================================================
# ResolvedType structure
# ======================================================================

class TestResolvedType:
    def test_dataclass_fields(self):
        rt = ResolvedType("int32", frozenset({"int32"}), None)
        assert rt.annotation_expr == "int32"
        assert rt.import_names == frozenset({"int32"})
        assert rt.external_import is None

    def test_default_as_frozenset(self):
        rt = ResolvedType("bool")
        assert rt.import_names == frozenset()


# ======================================================================
# resolve_type — scalar primitives
# ======================================================================

class TestResolveScalarPrimitives:
    def test_int32(self):
        rt = resolve_type("int32")
        assert rt.annotation_expr == "int32"
        assert rt.import_names == frozenset({"int32"})
        assert rt.external_import is None

    def test_float64(self):
        rt = resolve_type("float64")
        assert rt.annotation_expr == "float64"
        assert "float64" in rt.import_names

    def test_bool(self):
        rt = resolve_type("bool")
        assert rt.annotation_expr == "bool"
        assert rt.import_names == frozenset()  # Python builtin

    def test_string(self):
        rt = resolve_type("string")
        assert rt.annotation_expr == "str"
        assert rt.import_names == frozenset()  # Python builtin

    def test_wstring(self):
        rt = resolve_type("wstring")
        assert rt.annotation_expr == "str"
        assert rt.import_names == frozenset()

    def test_uint8(self):
        rt = resolve_type("uint8")
        assert rt.annotation_expr == "uint8"

    def test_int64(self):
        rt = resolve_type("int64")
        assert rt.annotation_expr == "int64"

    def test_byte_maps_to_uint8(self):
        rt = resolve_type("byte")
        assert rt.annotation_expr == "uint8"

    def test_char_maps_to_uint8(self):
        rt = resolve_type("char")
        assert rt.annotation_expr == "uint8"


# ======================================================================
# resolve_type — time / duration (special external types)
# ======================================================================

class TestResolveTimeDuration:
    def test_time(self):
        rt = resolve_type("time")
        assert rt.annotation_expr == "Time"
        assert rt.external_import is not None
        assert "builtin_interfaces" in rt.external_import

    def test_duration(self):
        rt = resolve_type("duration")
        assert rt.annotation_expr == "Duration"
        assert rt.external_import is not None
        assert "builtin_interfaces" in rt.external_import

    def test_time_uppercase(self):
        rt = resolve_type("Time")
        assert rt.annotation_expr == "Time"

    def test_duration_uppercase(self):
        rt = resolve_type("Duration")
        assert rt.annotation_expr == "Duration"


# ======================================================================
# resolve_type — bounded string
# ======================================================================

class TestResolveBoundedString:
    def test_bounded_string(self):
        rt = resolve_type("string<=128")
        assert "bounded_str" in rt.annotation_expr
        assert "128" in rt.annotation_expr
        assert rt.import_names == frozenset({"bounded_str"})
        assert rt.external_import is None

    def test_bounded_wstring(self):
        rt = resolve_type("wstring<=10")
        assert "bounded_str" in rt.annotation_expr
        assert "10" in rt.annotation_expr

    def test_bounded_string_value_of_1(self):
        rt = resolve_type("string<=1")
        assert "bounded_str[1]" in rt.annotation_expr


# ======================================================================
# resolve_type — arrays
# ======================================================================

class TestResolveArrays:
    def test_unbounded_array(self):
        rt = resolve_type("int32[]")
        assert "sequence" in rt.annotation_expr
        assert "int32" in rt.annotation_expr
        assert "sequence" in rt.import_names
        assert "int32" in rt.import_names

    def test_fixed_array(self):
        rt = resolve_type("float64[3]")
        assert "array" in rt.annotation_expr
        assert "float64" in rt.annotation_expr
        assert "3" in rt.annotation_expr
        assert "array" in rt.import_names

    def test_bounded_array(self):
        rt = resolve_type("int32[<=5]")
        assert "sequence" in rt.annotation_expr
        assert "5" in rt.annotation_expr

    def test_uint8_unbounded_array(self):
        rt = resolve_type("uint8[]")
        assert "sequence[uint8]" in rt.annotation_expr

    def test_string_unbounded_array(self):
        rt = resolve_type("string[]")
        assert "sequence[str]" in rt.annotation_expr

    def test_bounded_string_array(self):
        rt = resolve_type("string<=255[]")
        assert "sequence" in rt.annotation_expr
        assert "bounded_str" in rt.annotation_expr

    def test_nested_type_array(self):
        rt = resolve_type("std_msgs/msg/String[]", current_package="test")
        assert "sequence" in rt.annotation_expr
        assert rt.external_import is not None


# ======================================================================
# resolve_type — sequences
# ======================================================================

class TestResolveSequences:
    def test_unbounded_sequence(self):
        rt = resolve_type("sequence<uint8>")
        assert "sequence[uint8]" in rt.annotation_expr
        assert "sequence" in rt.import_names
        assert "uint8" in rt.import_names

    def test_bounded_sequence(self):
        rt = resolve_type("sequence<uint8,10>")
        assert "sequence" in rt.annotation_expr
        assert "uint8" in rt.annotation_expr
        assert "10" in rt.annotation_expr

    def test_sequence_of_float64(self):
        rt = resolve_type("sequence<float64>")
        assert "sequence[float64]" in rt.annotation_expr

    def test_sequence_of_nested_type(self):
        rt = resolve_type(
            "sequence<std_msgs/msg/String>", current_package="test",
        )
        assert rt.external_import is not None
        assert "String" in rt.annotation_expr

    def test_bounded_sequence_of_nested_type(self):
        rt = resolve_type(
            "sequence<geometry_msgs/msg/Point,5>", current_package="test",
        )
        assert "5" in rt.annotation_expr
        assert rt.external_import is not None


# ======================================================================
# resolve_type — nested types
# ======================================================================

class TestResolveNestedTypes:
    def test_fully_qualified_three_part(self):
        rt = resolve_type("std_msgs/msg/String", current_package="test")
        assert rt.annotation_expr == "String"
        assert rt.external_import is not None
        assert "std_msgs" in rt.external_import
        assert "_string" in rt.external_import

    def test_two_part_normalised(self):
        rt = resolve_type("std_msgs/String", current_package="test")
        assert rt.annotation_expr == "String"
        assert rt.external_import is not None
        # external_import uses dotted Python path, not filesystem slashes
        assert ".msg." in rt.external_import

    def test_unqualified_in_current_package(self):
        rt = resolve_type("String", current_package="my_pkg")
        assert "my_pkg" in rt.external_import
        assert rt.annotation_expr == "String"

    def test_with_root_package_prefix(self):
        rt = resolve_type(
            "std_msgs/msg/String",
            current_package="test",
            root_package="zros2_msgs",
        )
        assert "zros2_msgs.std_msgs" in rt.external_import

    def test_srv_type_reference(self):
        rt = resolve_type(
            "my_pkg/srv/Foo", current_package="test",
        )
        assert rt.annotation_expr == "Foo"
        assert "srv" in rt.external_import
        assert "_foo" in rt.external_import

    def test_action_type_reference(self):
        rt = resolve_type(
            "my_pkg/action/Bar", current_package="test",
        )
        assert rt.annotation_expr == "Bar"
        assert "action" in rt.external_import

    def test_cross_package_without_msg(self):
        """'pkg/Type' without /msg/ should resolve to pkg/msg/Type."""
        rt = resolve_type("my_pkg/Header", current_package="other")
        assert rt.annotation_expr == "Header"
        assert "my_pkg.msg._header" in rt.external_import


# ======================================================================
# resolve_type — edge cases
# ======================================================================

class TestResolveTypeEdgeCases:
    def test_unknown_type_falls_through_to_identifier(self):
        """When Lark can't parse, the raw string becomes base_name."""
        rt = resolve_type("SomeUnknownType")
        assert rt.annotation_expr == "SomeUnknownType"
        assert rt.external_import is not None

    def test_empty_string(self):
        rt = resolve_type("")
        assert rt.annotation_expr == ""

    def test_whitespace_stripped(self):
        rt = resolve_type("  int32  ")
        assert rt.annotation_expr == "int32"

    def test_sequence_of_time(self):
        rt = resolve_type("sequence<time>")
        assert "Time" in rt.annotation_expr
        assert rt.external_import is not None

    def test_array_of_duration(self):
        rt = resolve_type("duration[]")
        assert "sequence" in rt.annotation_expr
        assert "Duration" in rt.annotation_expr


# ======================================================================
# is_primitive
# ======================================================================

class TestIsPrimitive:
    def test_primitives(self):
        assert is_primitive("int32")
        assert is_primitive("float64")
        assert is_primitive("string")
        assert is_primitive("bool")
        assert is_primitive("uint8")
        assert is_primitive("int8")
        assert is_primitive("byte")
        assert is_primitive("char")

    def test_time_and_duration(self):
        assert is_primitive("time")
        assert is_primitive("duration")

    def test_bounded_string_not_primitive(self):
        assert not is_primitive("string<=128")

    def test_nested_type_not_primitive(self):
        assert not is_primitive("std_msgs/msg/Header")

    def test_arrays_of_primitives_are_primitives(self):
        assert is_primitive("int32[3]")
        assert is_primitive("float64[]")
        assert is_primitive("int32[<=5]")

    def test_sequences_of_primitives_are_primitives(self):
        assert is_primitive("sequence<uint8>")
        assert is_primitive("sequence<int32,10>")

    def test_sequence_of_nested_not_primitive(self):
        assert not is_primitive("sequence<std_msgs/Header>")

    def test_empty_string_not_primitive(self):
        assert not is_primitive("")

    def test_gibberish_not_primitive(self):
        assert not is_primitive("@#$%")


# ======================================================================
# get_default_value (alias for _default_expr)
# ======================================================================

class TestGetDefaultValue:
    def test_int(self):
        assert get_default_value("int32") == "0"
        assert get_default_value("uint8") == "0"
        assert get_default_value("int64") == "0"

    def test_float(self):
        assert get_default_value("float32") == "0.0"
        assert get_default_value("float64") == "0.0"

    def test_string(self):
        assert get_default_value("string") == '""'
        assert get_default_value("wstring") == '""'

    def test_bool(self):
        assert get_default_value("bool") == "False"

    def test_unbounded_array(self):
        assert get_default_value("int32[]") == "()"

    def test_fixed_array(self):
        assert get_default_value("float64[3]") == "()"

    def test_uint8_fixed_array(self):
        assert get_default_value("uint8[16]") == "(0,) * 16"

    def test_sequence(self):
        assert get_default_value("sequence<uint8>") == "()"
        assert get_default_value("sequence<float64, 5>") == "()"

    def test_bounded_string(self):
        assert get_default_value("string<=255") == '""'

    def test_time(self):
        assert get_default_value("time") == "None"

    def test_duration(self):
        assert get_default_value("duration") == "None"

    def test_nested_type(self):
        assert get_default_value("std_msgs/msg/Header") == "None"

    def test_unknown_or_empty(self):
        assert get_default_value("") == "None"
        assert get_default_value("garbage") == "None"
