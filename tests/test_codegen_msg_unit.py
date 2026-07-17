"""Component-level tests for ``zros2.generator._codegen._msg``.

Tests the core message module code generator in isolation:
- ``GeneratedFile`` data type
- ``_registry_import`` helper
- ``_needs_optional_annotation`` heuristic
- ``generate_message_module`` output structure, correctness, and syntax
- Generated code can be compiled and produces valid dataclass-like classes
"""

import hashlib
import pathlib

from zros2.generator._codegen._msg import (
    GeneratedFile,
    _registry_import,
    _needs_optional_annotation,
    generate_message_module,
)
from zros2.generator._parser import MsgDefinition, MsgField


# ======================================================================
# GeneratedFile
# ======================================================================

class TestGeneratedFile:
    def test_fields(self):
        gf = GeneratedFile(path=pathlib.Path("a/b.py"), content="code")
        assert gf.path == pathlib.Path("a/b.py")
        assert gf.content == "code"

    def test_is_namedtuple(self):
        gf = GeneratedFile(path=pathlib.Path("x.py"), content="y")
        p, c = gf
        assert p == pathlib.Path("x.py")
        assert c == "y"


# ======================================================================
# _registry_import
# ======================================================================

class TestRegistryImport:
    def test_no_root_package(self):
        assert _registry_import("") == "_registry"

    def test_with_root_package(self):
        assert _registry_import("zros2_msgs") == "zros2_msgs._registry"

    def test_with_nested_root_package(self):
        assert _registry_import("my.workspace.msgs") == "my.workspace.msgs._registry"


# ======================================================================
# _needs_optional_annotation
# ======================================================================

class TestNeedsOptionalAnnotation:
    def test_nested_type_with_none_default_needs_optional(self):
        assert _needs_optional_annotation("None", "Header")

    def test_primitive_with_none_default_does_not_need_optional(self):
        assert not _needs_optional_annotation("None", "int32")
        assert not _needs_optional_annotation("None", "float64")
        assert not _needs_optional_annotation("None", "bool")
        assert not _needs_optional_annotation("None", "str")
        assert not _needs_optional_annotation("None", "uint8")

    def test_non_none_default_does_not_need_optional(self):
        assert not _needs_optional_annotation("0", "int32")
        assert not _needs_optional_annotation('""', "str")
        assert not _needs_optional_annotation("False", "bool")

    def test_sequence_type_with_none_default_needs_optional(self):
        assert _needs_optional_annotation("None", "sequence[float64]")
        assert _needs_optional_annotation("None", "array[float64, 3]")


# ======================================================================
# generate_message_module — structure checks
# ======================================================================

class TestGenerateMessageStructure:
    """Check that the generated source has the expected structural elements."""

    def test_class_name_in_output(self):
        defn = MsgDefinition(
            package="test", type_name="Point", type_kind="msg",
            fields=[
                MsgField(name="x", type_str="float64"),
                MsgField(name="y", type_str="float64"),
            ],
        )
        code = generate_message_module(defn)
        assert "class Point(IdlStruct):" in code

    def test_decorator_present(self):
        defn = MsgDefinition(
            package="test", type_name="Foo", type_kind="msg",
            fields=[MsgField(name="val", type_str="int32")],
        )
        code = generate_message_module(defn)
        assert "@dataclass(init=False)" in code

    def test_hand_written_init(self):
        defn = MsgDefinition(
            package="test", type_name="Foo", type_kind="msg",
            fields=[MsgField(name="val", type_str="int32")],
        )
        code = generate_message_module(defn)
        # Should have a keyword-only __init__
        assert "def __init__(self, *, val: int32=0) -> None:" in code

    def test_imports_present(self):
        defn = MsgDefinition(
            package="test", type_name="Foo", type_kind="msg",
            fields=[MsgField(name="val", type_str="int32")],
        )
        code = generate_message_module(defn)
        assert "from dataclasses import dataclass" in code
        assert "from pycdr2 import IdlStruct" in code
        assert "from pycdr2.types import int32" in code

    def test_utility_methods_present(self):
        defn = MsgDefinition(
            package="test", type_name="Foo", type_kind="msg",
            fields=[MsgField(name="val", type_str="int32")],
        )
        code = generate_message_module(defn)
        assert "from_attributes" in code
        assert "from_dict" in code
        assert "to_dict" in code
        assert "serialize" not in code  # inherited from IdlStruct

    def test_annotations_override(self):
        defn = MsgDefinition(
            package="test", type_name="Foo", type_kind="msg",
            fields=[MsgField(name="val", type_str="int32")],
        )
        code = generate_message_module(defn)
        assert "__annotations__" in code

    def test_annotations_contains_default_factory_fields(self):
        """Nested/external types (time, Header, etc.) must appear in
        ``__annotations__`` so that ``@dataclass(init=False)`` can
        find their type annotation at class-build time."""
        defn = MsgDefinition(
            package="test", type_name="Foo", type_kind="msg",
            fields=[MsgField(name="stamp", type_str="time")],
        )
        code = generate_message_module(defn)
        # The __annotations__ override must include the field;
        # previously it was ``{}`` because the append-to-annotations
        # code was accidentally inside the wrong branch.
        assert "'stamp': Time" in code

    def test_header_comment(self):
        defn = MsgDefinition(
            package="test", type_name="Foo", type_kind="msg",
            fields=[],
        )
        code = generate_message_module(defn)
        assert "DO NOT MODIFY" in code
        assert "Generated at:" in code

    def test_header_sha1(self):
            """SHA1 hash in header matches the body content."""
            defn = MsgDefinition(
                package="test", type_name="Foo", type_kind="msg",
                fields=[MsgField(name="val", type_str="int32")],
            )
            code = generate_message_module(defn)
            sha_line = [line for line in code.splitlines() if line.startswith("# SHA1:")][0]
            sha_value = sha_line.split(": ", 1)[1]
            body = code.split("\n\n", 1)[1]
            expected = hashlib.sha1(body.encode("utf-8")).hexdigest()
            assert sha_value == expected

    def test_generated_metadata_present(self):
        defn = MsgDefinition(
            package="test", type_name="Point", type_kind="msg",
            fields=[MsgField(name="x", type_str="float64")],
        )
        code = generate_message_module(defn)
        assert "__generated__ = True" in code
        assert "zros2-gen v" in code
        assert "__source__ = 'test/msg/Point.msg'" in code

    def test_metadata_not_in_annotations(self):
        """Module-level metadata (__generated__, __generator__, __source__)
        must NOT appear in the class-level ``__annotations__`` dict, which
        should only contain CDR field types."""
        defn = MsgDefinition(
            package="test", type_name="Foo", type_kind="msg",
            fields=[MsgField(name="val", type_str="int32")],
        )
        code = generate_message_module(defn)
        # Find the __annotations__ override dict
        import ast as _ast
        tree = _ast.parse(code)
        cls_def = next(n for n in _ast.walk(tree)
                       if isinstance(n, _ast.ClassDef))
        ann_assign = next(
            (n for n in cls_def.body
             if isinstance(n, _ast.Assign)
             and any(t.id == "__annotations__" for t in n.targets
                     if isinstance(t, _ast.Name))),
            None,
        )
        assert ann_assign is not None, "__annotations__ override not found"
        ann_str = _ast.unparse(ann_assign.value)
        assert "__generated__" not in ann_str, \
            "__generated__ leaked into __annotations__"
        assert "__source__" not in ann_str, \
            "__source__ leaked into __annotations__"

# ======================================================================
# generate_message_module — field and constant output
# ======================================================================

class TestGenerateMessageFields:
    def test_primitive_field_default(self):
        defn = MsgDefinition(
            package="test", type_name="Bar", type_kind="msg",
            fields=[MsgField(name="count", type_str="int32")],
        )
        code = generate_message_module(defn)
        assert "count: int32 = 0" in code

    def test_string_field_default(self):
        defn = MsgDefinition(
            package="test", type_name="Bar", type_kind="msg",
            fields=[MsgField(name="name", type_str="string")],
        )
        code = generate_message_module(defn)
        assert "name: str=''" in code

    def test_bool_field_default(self):
        defn = MsgDefinition(
            package="test", type_name="Bar", type_kind="msg",
            fields=[MsgField(name="flag", type_str="bool")],
        )
        code = generate_message_module(defn)
        assert "flag: bool = False" in code

    def test_nested_field_with_factory(self):
        defn = MsgDefinition(
            package="test", type_name="Bar", type_kind="msg",
            fields=[MsgField(name="header", type_str="std_msgs/msg/Header")],
        )
        code = generate_message_module(defn)
        assert "field(default_factory=Header)" in code

    def test_constant_with_classvar(self):
        defn = MsgDefinition(
            package="test", type_name="Bar", type_kind="msg",
            constants=[MsgField(name="FOO", type_str="int32",
                                default="42", is_constant=True)],
        )
        code = generate_message_module(defn)
        assert "ClassVar" in code
        assert "FOO: ClassVar[int32] = 42" in code

    def test_bool_constant(self):
        defn = MsgDefinition(
            package="test", type_name="Bar", type_kind="msg",
            constants=[MsgField(name="ENABLED", type_str="bool",
                                default="True", is_constant=True)],
        )
        code = generate_message_module(defn)
        assert "ENABLED: ClassVar[bool] = True" in code

    def test_bool_constant_lowercase_true(self):
        defn = MsgDefinition(
            package="test", type_name="Bar", type_kind="msg",
            constants=[MsgField(name="FLAG", type_str="bool",
                                default="true", is_constant=True)],
        )
        code = generate_message_module(defn)
        assert "True" in code  # normalised

    def test_bool_constant_1(self):
        defn = MsgDefinition(
            package="test", type_name="Bar", type_kind="msg",
            constants=[MsgField(name="FLAG", type_str="bool",
                                default="1", is_constant=True)],
        )
        code = generate_message_module(defn)
        assert "True" in code

    def test_bool_constant_0(self):
        defn = MsgDefinition(
            package="test", type_name="Bar", type_kind="msg",
            constants=[MsgField(name="FLAG", type_str="bool",
                                default="0", is_constant=True)],
        )
        code = generate_message_module(defn)
        assert "False" in code

    def test_constant_with_external_import(self):
        """A constant whose type requires an external import (time/duration)."""
        defn = MsgDefinition(
            package="test", type_name="Bar", type_kind="msg",
            constants=[MsgField(name="NOW", type_str="time",
                                default="0", is_constant=True)],
        )
        code = generate_message_module(defn)
        # The time type adds an external import for builtin_interfaces
        assert "builtin_interfaces" in code
        assert "ClassVar" in code

    def test_float64_array_field(self):
        defn = MsgDefinition(
            package="test", type_name="Bar", type_kind="msg",
            fields=[MsgField(name="values", type_str="float64[3]")],
        )
        code = generate_message_module(defn)
        assert "array[float64, 3]" in code

    def test_sequence_field(self):
        defn = MsgDefinition(
            package="test", type_name="Bar", type_kind="msg",
            fields=[MsgField(name="data", type_str="sequence<uint8>")],
        )
        code = generate_message_module(defn)
        assert "sequence[uint8]" in code

    def test_bounded_string_field(self):
        defn = MsgDefinition(
            package="test", type_name="Bar", type_kind="msg",
            fields=[MsgField(name="name", type_str="string<=128")],
        )
        code = generate_message_module(defn)
        assert "bounded_str[128]" in code

    def test_field_default_is_type_based_not_field_based(self):
        """The codegen currently uses _default_expr(type) rather than field.default."""
        defn = MsgDefinition(
            package="test", type_name="Bar", type_kind="msg",
            fields=[MsgField(name="x", type_str="int32", default="42")],
        )
        code = generate_message_module(defn)
        # Known limitation: field.default is not used; default is from type.
        assert "x: int32=0" in code


# ======================================================================
# generate_message_module — root_package handling
# ======================================================================

class TestGenerateMessageRootPackage:
    def test_root_package_in_nested_import(self):
        defn = MsgDefinition(
            package="test", type_name="Bar", type_kind="msg",
            fields=[MsgField(name="h", type_str="std_msgs/msg/Header")],
        )
        code = generate_message_module(defn, root_package="zros2_msgs")
        # The external import should reference the root package
        assert "zros2_msgs.std_msgs" in code

    def test_root_package_in_registry_import(self):
        defn = MsgDefinition(
            package="test", type_name="Foo", type_kind="msg",
            fields=[MsgField(name="x", type_str="int32")],
        )
        code = generate_message_module(defn, root_package="my_msgs")
        # No direct registry import in _msg.py, but let's ensure it still works
        assert "class Foo(IdlStruct):" in code


# ======================================================================
# generate_message_module — syntax validation
# ======================================================================

class TestGenerateMessageSyntax:
    """Every generated module must be valid Python."""

    def test_simple_compiles(self):
        defn = MsgDefinition(
            package="test", type_name="Foo", type_kind="msg",
            fields=[MsgField(name="x", type_str="int32")],
        )
        code = generate_message_module(defn)
        compile(code, "<test>", "exec")

    def test_empty_message_compiles(self):
        defn = MsgDefinition(
            package="test", type_name="Empty", type_kind="msg",
            fields=[],
        )
        code = generate_message_module(defn)
        compile(code, "<test>", "exec")

    def test_complex_message_compiles(self):
        defn = MsgDefinition(
            package="test", type_name="Complex", type_kind="msg",
            fields=[
                MsgField(name="x", type_str="int32"),
                MsgField(name="y", type_str="float64"),
                MsgField(name="label", type_str="string"),
                MsgField(name="flag", type_str="bool"),
                MsgField(name="values", type_str="float64[]"),
                MsgField(name="fixed", type_str="uint8[16]"),
                MsgField(name="bounded", type_str="string<=255"),
                MsgField(name="seq", type_str="sequence<int32,10>"),
            ],
        )
        code = generate_message_module(defn)
        compile(code, "<test>", "exec")

    def test_nested_type_compiles(self):
        defn = MsgDefinition(
            package="test", type_name="WithHeader", type_kind="msg",
            fields=[MsgField(name="header", type_str="std_msgs/msg/Header")],
        )
        code = generate_message_module(defn)
        compile(code, "<test>", "exec")

    def test_constants_compile(self):
        defn = MsgDefinition(
            package="test", type_name="WithConst", type_kind="msg",
            fields=[MsgField(name="x", type_str="int32")],
            constants=[
                MsgField(name="FOO", type_str="int32",
                         default="42", is_constant=True),
                MsgField(name="BAR", type_str="float64",
                         default="3.14", is_constant=True),
            ],
        )
        code = generate_message_module(defn)
        compile(code, "<test>", "exec")


# ======================================================================
# generate_message_module — empty / no-field edge cases
# ======================================================================

class TestGenerateMessageEdgeCases:
    def test_no_fields_no_constants(self):
        defn = MsgDefinition(
            package="test", type_name="Empty", type_kind="msg",
        )
        code = generate_message_module(defn)
        # With zero fields the __init__ body is ``pass``, which is valid.
        compile(code, "<test>", "exec")

    def test_only_constants(self):
        defn = MsgDefinition(
            package="test", type_name="ConstOnly", type_kind="msg",
            constants=[MsgField(name="VERSION", type_str="int32",
                                default="1", is_constant=True)],
        )
        code = generate_message_module(defn)
        assert "ClassVar" in code
        compile(code, "<test>", "exec")

    def test_field_name_with_dash(self):
        """Type names with dashes are replaced by underscores."""
        defn = MsgDefinition(
            package="test", type_name="my-type", type_kind="msg",
            fields=[MsgField(name="val", type_str="int32")],
        )
        code = generate_message_module(defn)
        assert "class my_type(IdlStruct):" in code

    def test_srv_kind(self):
        """The type_kind appears in the module docstring."""
        defn = MsgDefinition(
            package="test", type_name="Foo_Request", type_kind="srv",
            fields=[MsgField(name="x", type_str="int32")],
        )
        code = generate_message_module(defn)
        lines = code.splitlines()
        doc_lines = [line for line in lines if 'Auto-generated' in line]
        assert any('srv' in line for line in doc_lines)
        assert "class Foo_Request(IdlStruct):" in code

    def test_optional_annotation_in_init_for_nested(self):
        """Nested types default to an empty instance, NOT Optional."""
        defn = MsgDefinition(
            package="test", type_name="Foo", type_kind="msg",
            fields=[MsgField(name="h", type_str="std_msgs/msg/Header")],
        )
        code = generate_message_module(defn)
        # The __init__ signature uses the bare type with a factory default,
        # not Optional, because the default is a concrete empty instance.
        assert "Optional[Header]" not in code
        assert "h: Header=Header()" in code or "h: Header = Header()" in code

    def test_no_optional_for_primitives(self):
        """Primitives defaulting to None DO NOT get Optional."""
        defn = MsgDefinition(
            package="test", type_name="Foo", type_kind="msg",
            fields=[MsgField(name="x", type_str="int32", default="0")],
        )
        code = generate_message_module(defn)
        # Check the __init__ signature
        assert "int32=0" in code  # ast.unparse omits spaces around =
        # Optional should NOT appear for primitives
        assert "typing import Optional" not in code

    def test_constant_time_external_import(self):
            """A ``time`` constant triggers an external import in generated code."""
            defn = MsgDefinition(
                package="test", type_name="WithTime", type_kind="msg",
                constants=[MsgField(name="NOW", type_str="time",
                                    default="0", is_constant=True)],
            )
            code = generate_message_module(defn)
            assert "builtin_interfaces" in code
            assert code.count("builtin_interfaces") >= 1