"""Component-level tests for ``zros2.generator._codegen._pyi``.

Tests the stub (``.pyi``) generator in isolation:
- ``_stub_annotation`` type translation
- ``_make_stub_field`` helper
- ``generate_stub_module`` output structure and syntax
- Import deduplication and annotation correctness
"""

import hashlib

import ast
import pytest

from zros2.generator._codegen._pyi import (
    _stub_annotation,
    _make_stub_field,
    generate_stub_module,
)
from zros2.generator._parser import MsgDefinition, MsgField


# ======================================================================
# _stub_annotation — CDR annotation → pure-Python type hint
# ======================================================================

class TestStubAnnotation:
    """Translating pycdr2 annotation expressions to native Python types."""

    def test_primitive_int32(self):
        assert _stub_annotation("int32") == "int"

    def test_primitive_uint8(self):
        assert _stub_annotation("uint8") == "int"

    def test_primitive_float64(self):
        assert _stub_annotation("float64") == "float"

    def test_primitive_bool(self):
        assert _stub_annotation("bool") == "bool"

    def test_primitive_str(self):
        assert _stub_annotation("str") == "str"

    def test_primitive_string(self):
        assert _stub_annotation("string") == "str"

    def test_primitive_wstring(self):
        assert _stub_annotation("wstring") == "str"

    def test_primitive_byte(self):
        assert _stub_annotation("byte") == "int"

    def test_primitive_char(self):
        assert _stub_annotation("char") == "int"

    def test_sequence_unbounded(self):
        assert _stub_annotation("sequence[int32]") == "Sequence[int]"

    def test_sequence_bounded(self):
        # Bounded size is preserved in the annotation (not stripped).
        result = _stub_annotation("sequence[uint8, 10]")
        assert "Sequence" in result
        assert "int" in result

    def test_array_fixed(self):
        assert _stub_annotation("array[float64, 3]") == "tuple[float, ...]"

    def test_array_fixed_int(self):
        assert _stub_annotation("array[int32, 16]") == "tuple[int, ...]"

    def test_bounded_str(self):
        assert _stub_annotation("bounded_str[128]") == "str"
        assert _stub_annotation("bounded_str[255]") == "str"

    def test_sequence_of_sequence(self):
        result = _stub_annotation("sequence[sequence[uint8]]")
        # Outer ``sequence`` is mapped to ``Sequence``; the inner one stays
        # lowercase because the regex only does one pass (non-recursive).
        assert result == "Sequence[sequence[int]]"

    def test_nested_type_preserved(self):
        assert _stub_annotation("Header") == "Header"
        assert _stub_annotation("Point") == "Point"

    def test_fully_qualified_type_preserved(self):
        assert _stub_annotation("String") == "String"

    def test_no_mapping_needed(self):
        assert _stub_annotation("SomeCustomType") == "SomeCustomType"


# ======================================================================
# generate_stub_module — structure checks
# ======================================================================

class TestGenerateStubStructure:
    def test_class_name(self):
        defn = MsgDefinition(
            package="test", type_name="Point", type_kind="msg",
            fields=[MsgField(name="x", type_str="float64")],
        )
        stub = generate_stub_module(defn)
        assert "class Point:" in stub

    def test_init_signature(self):
        defn = MsgDefinition(
            package="test", type_name="Point", type_kind="msg",
            fields=[MsgField(name="x", type_str="float64")],
        )
        stub = generate_stub_module(defn)
        assert "def __init__(self, *, x: float=0.0) -> None:" in stub

    def test_methods_present(self):
        defn = MsgDefinition(
            package="test", type_name="Point", type_kind="msg",
            fields=[MsgField(name="x", type_str="float64")],
        )
        stub = generate_stub_module(defn)
        assert "def serialize(self) -> bytes:" in stub
        assert "def deserialize(cls, data: bytes) -> Point:" in stub
        assert "def from_dict" in stub
        assert "def from_attributes" in stub
        assert "def to_dict(self) -> dict[str, object]:" in stub

    def test_header_present(self):
        defn = MsgDefinition(
            package="test", type_name="Foo", type_kind="msg",
            fields=[],
        )
        stub = generate_stub_module(defn)
        assert "DO NOT MODIFY" in stub

    def test_header_sha1(self):
        """SHA1 hash in header matches the stub body content."""
        defn = MsgDefinition(
            package="test", type_name="Foo", type_kind="msg",
            fields=[MsgField(name="x", type_str="float64")],
        )
        stub = generate_stub_module(defn)
        sha_line = [l for l in stub.splitlines() if l.startswith("# SHA1:")][0]
        sha_value = sha_line.split(": ", 1)[1]
        body = stub.split("\n\n", 1)[1]
        expected = hashlib.sha1(body.encode("utf-8")).hexdigest()
        assert sha_value == expected

    def test_generated_metadata_present(self):
        defn = MsgDefinition(
            package="test", type_name="Point", type_kind="msg",
            fields=[MsgField(name="x", type_str="float64")],
        )
        stub = generate_stub_module(defn)
        assert "__generated__ = True" in stub
        assert "zros2-gen v" in stub
        assert "__source__ = 'test/msg/Point.msg'" in stub


# ======================================================================
# generate_stub_module — field annotation correctness
# ======================================================================

class TestGenerateStubFields:
    def test_primitive_field_type(self):
        defn = MsgDefinition(
            package="test", type_name="Foo", type_kind="msg",
            fields=[MsgField(name="val", type_str="int32")],
        )
        stub = generate_stub_module(defn)
        assert "val: int" in stub

    def test_float_field_type(self):
        defn = MsgDefinition(
            package="test", type_name="Foo", type_kind="msg",
            fields=[MsgField(name="val", type_str="float64")],
        )
        stub = generate_stub_module(defn)
        assert "val: float" in stub

    def test_string_field(self):
        defn = MsgDefinition(
            package="test", type_name="Foo", type_kind="msg",
            fields=[MsgField(name="name", type_str="string")],
        )
        stub = generate_stub_module(defn)
        assert "name: str" in stub

    def test_bool_field(self):
        defn = MsgDefinition(
            package="test", type_name="Foo", type_kind="msg",
            fields=[MsgField(name="flag", type_str="bool")],
        )
        stub = generate_stub_module(defn)
        assert "flag: bool" in stub

    def test_array_field(self):
        defn = MsgDefinition(
            package="test", type_name="Foo", type_kind="msg",
            fields=[MsgField(name="values", type_str="float64[3]")],
        )
        stub = generate_stub_module(defn)
        assert "tuple[float, ...]" in stub

    def test_sequence_field(self):
        defn = MsgDefinition(
            package="test", type_name="Foo", type_kind="msg",
            fields=[MsgField(name="data", type_str="sequence<uint8>")],
        )
        stub = generate_stub_module(defn)
        assert "Sequence[int]" in stub

    def test_sequence_import_present(self):
        defn = MsgDefinition(
            package="test", type_name="Foo", type_kind="msg",
            fields=[MsgField(name="data", type_str="sequence<uint8>")],
        )
        stub = generate_stub_module(defn)
        assert "from collections.abc import Sequence" in stub

    def test_bounded_string_field(self):
        defn = MsgDefinition(
            package="test", type_name="Foo", type_kind="msg",
            fields=[MsgField(name="name", type_str="string<=128")],
        )
        stub = generate_stub_module(defn)
        assert "name: str" in stub

    def test_nested_type_field(self):
        defn = MsgDefinition(
            package="test", type_name="Foo", type_kind="msg",
            fields=[MsgField(name="header", type_str="std_msgs/msg/Header")],
        )
        stub = generate_stub_module(defn)
        assert "header: Header" in stub


# ======================================================================
# generate_stub_module — constant handling
# ======================================================================

class TestGenerateStubConstants:
    def test_constant_with_classvar(self):
        defn = MsgDefinition(
            package="test", type_name="Foo", type_kind="msg",
            constants=[MsgField(name="FOO", type_str="int32",
                                default="42", is_constant=True)],
        )
        stub = generate_stub_module(defn)
        assert "ClassVar[int]" in stub
        assert "FOO: ClassVar[int]" in stub
        assert "from typing import ClassVar" in stub

    def test_multiple_constants(self):
        defn = MsgDefinition(
            package="test", type_name="Foo", type_kind="msg",
            constants=[
                MsgField(name="A", type_str="int32",
                         default="1", is_constant=True),
                MsgField(name="B", type_str="float64",
                         default="2.0", is_constant=True),
            ],
        )
        stub = generate_stub_module(defn)
        assert "ClassVar[int]" in stub
        assert "ClassVar[float]" in stub

    def test_constant_with_external_import(self):
        """A constant with a type needing external import (time/duration)."""
        defn = MsgDefinition(
            package="test", type_name="Foo", type_kind="msg",
            constants=[MsgField(name="NOW", type_str="time",
                                default="0", is_constant=True)],
        )
        stub = generate_stub_module(defn)
        assert "ClassVar" in stub
        assert "builtin_interfaces" in stub


# ======================================================================
# generate_stub_module — syntax validation
# ======================================================================

class TestGenerateStubSyntax:
    def test_simple_stub_compiles(self):
        defn = MsgDefinition(
            package="test", type_name="Foo", type_kind="msg",
            fields=[MsgField(name="x", type_str="int32")],
        )
        stub = generate_stub_module(defn)
        # .pyi files are NOT valid Python modules (they use ... as body),
        # so we check syntax via the ast module on a best-effort basis.
        tree = ast.parse(stub)
        assert tree is not None

    def test_complex_stub_parses(self):
        defn = MsgDefinition(
            package="test", type_name="Complex", type_kind="msg",
            fields=[
                MsgField(name="x", type_str="int32"),
                MsgField(name="y", type_str="float64"),
                MsgField(name="data", type_str="sequence<uint8>"),
                MsgField(name="header", type_str="std_msgs/msg/Header"),
            ],
        )
        stub = generate_stub_module(defn)
        tree = ast.parse(stub)
        assert tree is not None

    def test_stub_with_constants_parses(self):
        defn = MsgDefinition(
            package="test", type_name="Foo", type_kind="msg",
            fields=[MsgField(name="x", type_str="int32")],
            constants=[MsgField(name="FOO", type_str="int32",
                                default="42", is_constant=True)],
        )
        stub = generate_stub_module(defn)
        tree = ast.parse(stub)
        assert tree is not None

    def test_empty_msg_stub_parses(self):
        defn = MsgDefinition(
            package="test", type_name="Empty", type_kind="msg",
            fields=[],
        )
        stub = generate_stub_module(defn)
        tree = ast.parse(stub)
        assert tree is not None


# ======================================================================
# generate_stub_module — edge cases
# ======================================================================

class TestGenerateStubEdgeCases:
    def test_no_sequence_import_when_no_sequence(self):
        defn = MsgDefinition(
            package="test", type_name="Foo", type_kind="msg",
            fields=[MsgField(name="x", type_str="int32")],
        )
        stub = generate_stub_module(defn)
        assert "from collections.abc import Sequence" not in stub

    def test_sequence_imported_only_once(self):
        defn = MsgDefinition(
            package="test", type_name="Foo", type_kind="msg",
            fields=[
                MsgField(name="a", type_str="sequence<uint8>"),
                MsgField(name="b", type_str="sequence<float64>"),
            ],
        )
        stub = generate_stub_module(defn)
        assert stub.count("from collections.abc import Sequence") == 1

    def test_external_import_in_stub(self):
        defn = MsgDefinition(
            package="test", type_name="Foo", type_kind="msg",
            fields=[MsgField(name="header", type_str="std_msgs/msg/Header")],
        )
        stub = generate_stub_module(defn)
        # The stub should include the external import
        assert "std_msgs" in stub

    def test_docstring_present(self):
        defn = MsgDefinition(
            package="test", type_name="Foo", type_kind="msg",
            fields=[MsgField(name="x", type_str="int32")],
        )
        stub = generate_stub_module(defn)
        assert "Stub for" in stub


# ======================================================================
# _make_stub_field helper
# ======================================================================

class TestMakeStubField:
    """Direct tests for the ``_make_stub_field`` helper."""

    def test_primitive_field(self):
        from zros2.generator._codegen._pyi import _make_stub_field
        from zros2.generator._parser import MsgField, MsgDefinition
        field = MsgField(name="x", type_str="int32")
        defn = MsgDefinition(package="test", type_name="Foo", type_kind="msg")
        native, line, needs_seq = _make_stub_field(field, defn, "")
        assert native == "int"
        assert "x: int" in line
        assert not needs_seq

    def test_sequence_field(self):
        from zros2.generator._codegen._pyi import _make_stub_field
        from zros2.generator._parser import MsgField, MsgDefinition
        field = MsgField(name="data", type_str="sequence<uint8>")
        defn = MsgDefinition(package="test", type_name="Foo", type_kind="msg")
        native, line, needs_seq = _make_stub_field(field, defn, "")
        assert "Sequence" in native
        assert needs_seq

    def test_field_with_default(self):
        from zros2.generator._codegen._pyi import _make_stub_field
        from zros2.generator._parser import MsgField, MsgDefinition
        field = MsgField(name="x", type_str="int32", default="42")
        defn = MsgDefinition(package="test", type_name="Foo", type_kind="msg")
        _, line, _ = _make_stub_field(field, defn, "")
        assert "= 42" in line

    def test_nested_field_has_no_default_suffix(self):
        from zros2.generator._codegen._pyi import _make_stub_field
        from zros2.generator._parser import MsgField, MsgDefinition
        field = MsgField(name="header", type_str="std_msgs/msg/Header")
        defn = MsgDefinition(package="test", type_name="Foo", type_kind="msg")
        native, line, needs_seq = _make_stub_field(field, defn, "")
        assert "Header" in line
        assert "=" not in line  # no default for nested types
        assert not needs_seq
