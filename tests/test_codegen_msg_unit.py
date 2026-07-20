"""Component-level tests for ``zros2.generator._codegen._msg``.

Tests the core message module code generator in isolation:
- ``GeneratedFile`` data type
- ``_registry_import`` helper
- ``_needs_optional_annotation`` heuristic
- ``generate_message_module`` output structure, correctness, and syntax
- Generated code can be compiled and produces valid dataclass-like classes
"""

import ast
import hashlib
import pathlib
from typing import Any

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
        assert "__ros_name__: str = 'test/msg/Point'" in code

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


# ═══════════════════════════════════════════════════════════════════════════
# to_dict / from_dict runtime correctness
# ═══════════════════════════════════════════════════════════════════════════

def _clean(code: str) -> str:
    """Remove imports that won't resolve outside a full ROS package tree."""
    kept: list[str] = []
    for line in code.splitlines():
        if line.startswith("from ") and not any(
            line.startswith(f"from {p}")
            for p in ("typing", "dataclasses", "pycdr2", "zros2", "collections")
        ):
            continue
        kept.append(line)
    return "\n".join(kept)


def _exec_class(code: str, name: str | None = None) -> type:
    """Compile and exec generated source, return the generated class.

    If *name* is given, return that class by name.  Otherwise find it by
    looking for a type that has ``__ros_name__`` (a dunder set by the codegen
    on every generated message class).
    """
    ns: dict[str, Any] = {}
    exec(compile(ast.parse(_clean(code)), "<test>", "exec"), ns)
    if name:
        return ns[name]
    for v in ns.values():
        if isinstance(v, type) and hasattr(v, "__ros_name__"):
            return v
    raise RuntimeError("no generated class found")


def _exec_pair(code_a: str, code_b: str,
               name_a: str, name_b: str) -> tuple[type, type]:
    """Exec two generated modules in the same namespace (cross-ref support).

    Returns ``(type_a, type_b)`` by their expected class names.
    """
    ns: dict[str, Any] = {}
    exec(compile(ast.parse(_clean(code_a)), "<a>", "exec"), ns)
    exec(compile(ast.parse(_clean(code_b)), "<b>", "exec"), ns)
    return ns[name_a], ns[name_b]


class TestGeneratedToDictFromDict:
    """Execute generated to_dict/from_dict and verify correctness."""

    def test_flat_message(self):
        """Primitive fields: to_dict returns correct dict, from_dict roundtrips."""
        code = generate_message_module(MsgDefinition(
            package="test", type_name="Point", type_kind="msg",
            fields=[
                MsgField(name="x", type_str="float64"),
                MsgField(name="y", type_str="float64"),
                MsgField(name="label", type_str="string"),
            ],
        ))
        Point = _exec_class(code, "Point")
        p = Point(x=1.5, y=2.5, label="origin")

        d = p.to_dict()
        assert d == {"x": 1.5, "y": 2.5, "label": "origin"}

        p2 = Point.from_dict(d)
        assert p2.x == 1.5
        assert p2.y == 2.5
        assert p2.label == "origin"

    def test_array_field(self):
        """Primitive array field: to_dict returns list, from_dict roundtrips."""
        code = generate_message_module(MsgDefinition(
            package="test", type_name="WithArray", type_kind="msg",
            fields=[
                MsgField(name="values", type_str="float64[]"),
                MsgField(name="id", type_str="int32"),
            ],
        ))
        Cls = _exec_class(code, "WithArray")
        obj = Cls(values=[1.0, 2.0, 3.0], id=42)

        d = obj.to_dict()
        assert d == {"values": [1.0, 2.0, 3.0], "id": 42}

        obj2 = Cls.from_dict(d)
        assert obj2.id == 42
        assert list(obj2.values) == [1.0, 2.0, 3.0]

    def test_nested_message(self):
        """Nested message field: to_dict/from_dict recurse correctly."""
        inner_code = generate_message_module(MsgDefinition(
            package="nest", type_name="Inner", type_kind="msg",
            fields=[
                MsgField(name="x", type_str="float64"),
                MsgField(name="y", type_str="float64"),
            ],
        ))
        outer_code = generate_message_module(MsgDefinition(
            package="nest", type_name="Outer", type_kind="msg",
            fields=[
                MsgField(name="inner", type_str="nest/Inner"),
                MsgField(name="label", type_str="string"),
            ],
        ))
        Inner, Outer = _exec_pair(inner_code, outer_code, "Inner", "Outer")

        obj = Outer(inner=Inner(x=1.0, y=2.0), label="pt")
        d = obj.to_dict()
        assert d == {"inner": {"x": 1.0, "y": 2.0}, "label": "pt"}

        obj2 = Outer.from_dict(d)
        assert obj2.label == "pt"
        assert obj2.inner.x == 1.0
        assert obj2.inner.y == 2.0

    def test_nested_array(self):
        """Sequence of nested messages: list comprehension in to_dict/from_dict."""
        inner_code = generate_message_module(MsgDefinition(
            package="nest", type_name="Item", type_kind="msg",
            fields=[
                MsgField(name="val", type_str="int32"),
                MsgField(name="name", type_str="string"),
            ],
        ))
        outer_code = generate_message_module(MsgDefinition(
            package="nest", type_name="Container", type_kind="msg",
            fields=[
                MsgField(name="items", type_str="sequence<nest/Item>"),
                MsgField(name="id", type_str="int32"),
            ],
        ))
        Item, Container = _exec_pair(inner_code, outer_code, "Item", "Container")

        obj = Container(items=[Item(val=1, name="a"), Item(val=2, name="b")], id=99)
        d = obj.to_dict()
        assert d == {"items": [{"val": 1, "name": "a"}, {"val": 2, "name": "b"}], "id": 99}

        obj2 = Container.from_dict(d)
        assert obj2.id == 99
        assert len(obj2.items) == 2
        assert obj2.items[0].val == 1
        assert obj2.items[1].name == "b"

    def test_fixed_array_uint8(self):
        """Fixed-size primitive array (e.g. uint8[16] for UUID)."""
        code = generate_message_module(MsgDefinition(
            package="test", type_name="UUID", type_kind="msg",
            fields=[MsgField(name="uuid", type_str="uint8[16]")],
        ))
        Cls = _exec_class(code, "UUID")
        obj = Cls(uuid=(0,) * 16)
        d = obj.to_dict()
        assert "uuid" in d
        assert len(d["uuid"]) == 16

        obj2 = Cls.from_dict(d)
        assert len(obj2.uuid) == 16

    def test_all_field_types_roundtrip(self):
        """Message with every primitive type — comprehensive roundtrip."""
        code = generate_message_module(MsgDefinition(
            package="test", type_name="AllTypes", type_kind="msg",
            fields=[
                MsgField(name="a", type_str="int32"),
                MsgField(name="b", type_str="float64"),
                MsgField(name="c", type_str="string"),
                MsgField(name="d", type_str="bool"),
                MsgField(name="e", type_str="float64[]"),
                MsgField(name="f", type_str="uint8[4]"),
            ],
        ))
        Cls = _exec_class(code, "AllTypes")
        obj = Cls(a=42, b=3.14, c="hello", d=True, e=[1.0, 2.0], f=(10, 20, 30, 40))

        d = obj.to_dict()
        assert d["a"] == 42
        assert d["b"] == 3.14
        assert d["c"] == "hello"
        assert d["d"] is True
        assert list(d["e"]) == [1.0, 2.0]
        assert len(d["f"]) == 4

        obj2 = Cls.from_dict(d)
        assert obj2.a == 42
        assert abs(obj2.b - 3.14) < 1e-9
        assert obj2.c == "hello"
        assert obj2.d is True

    def test_empty_array(self):
        """Sequence field with empty list."""
        code = generate_message_module(MsgDefinition(
            package="test", type_name="EmptyArr", type_kind="msg",
            fields=[
                MsgField(name="values", type_str="float64[]"),
                MsgField(name="id", type_str="int32"),
            ],
        ))
        Cls = _exec_class(code, "EmptyArr")
        obj = Cls(values=[], id=0)

        d = obj.to_dict()
        assert d == {"values": [], "id": 0}

        obj2 = Cls.from_dict({"values": [], "id": 0})
        assert obj2.id == 0
        assert list(obj2.values) == []

    def test_bounded_string(self):
        """Bounded string field (string<=N)."""
        code = generate_message_module(MsgDefinition(
            package="test", type_name="Bounded", type_kind="msg",
            fields=[MsgField(name="name", type_str="string<=128")],
        ))
        Cls = _exec_class(code, "Bounded")
        obj = Cls(name="hello")

        d = obj.to_dict()
        assert d == {"name": "hello"}

        obj2 = Cls.from_dict({"name": "world"})
        assert obj2.name == "world"

    def test_from_dict_missing_key(self):
        """from_dict with missing field raises KeyError."""
        import pytest
        code = generate_message_module(MsgDefinition(
            package="test", type_name="WithField", type_kind="msg",
            fields=[MsgField(name="x", type_str="int32"),
                    MsgField(name="y", type_str="int32")],
        ))
        Cls = _exec_class(code, "WithField")
        with pytest.raises(KeyError):
            Cls.from_dict({"x": 1})

    def test_wide_nesting_roundtrip(self):
        """Outer with 3 inner branches — exercises multiple nested calls."""
        inner_code = generate_message_module(MsgDefinition(
            package="nest", type_name="Leaf", type_kind="msg",
            fields=[MsgField(name="val", type_str="int32")],
        ))
        outer_code = generate_message_module(MsgDefinition(
            package="nest", type_name="Wide", type_kind="msg",
            fields=[
                MsgField(name="left", type_str="nest/Leaf"),
                MsgField(name="right", type_str="nest/Leaf"),
                MsgField(name="center", type_str="nest/Leaf"),
            ],
        ))
        Leaf, Wide = _exec_pair(inner_code, outer_code, "Leaf", "Wide")

        obj = Wide(left=Leaf(val=1), right=Leaf(val=2), center=Leaf(val=3))
        d = obj.to_dict()
        assert d == {"left": {"val": 1}, "right": {"val": 2}, "center": {"val": 3}}

        obj2 = Wide.from_dict(d)
        assert obj2.left.val == 1
        assert obj2.right.val == 2
        assert obj2.center.val == 3

    def test_to_dict_from_dict_roundtrip_identity(self):
        """Roundtrip to_dict → from_dict preserves all values."""
        code = generate_message_module(MsgDefinition(
            package="test", type_name="Rt", type_kind="msg",
            fields=[
                MsgField(name="a", type_str="int32"),
                MsgField(name="b", type_str="float64"),
                MsgField(name="c", type_str="string"),
                MsgField(name="d", type_str="bool"),
            ],
        ))
        Cls = _exec_class(code, "Rt")
        original = Cls(a=1, b=2.0, c="x", d=True)
        restored = Cls.from_dict(original.to_dict())
        assert restored.a == 1
        assert restored.b == 2.0
        assert restored.c == "x"
        assert restored.d is True

    def test_deep_chain_roundtrip(self):
        """3-level deep chain: Outer → Mid → Inner."""
        leaf_code = generate_message_module(MsgDefinition(
            package="nest", type_name="Leaf", type_kind="msg",
            fields=[MsgField(name="val", type_str="int32")],
        ))
        mid_code = generate_message_module(MsgDefinition(
            package="nest", type_name="Mid", type_kind="msg",
            fields=[
                MsgField(name="child", type_str="nest/Leaf"),
                MsgField(name="val", type_str="int32"),
            ],
        ))
        top_code = generate_message_module(MsgDefinition(
            package="nest", type_name="Top", type_kind="msg",
            fields=[
                MsgField(name="child", type_str="nest/Mid"),
                MsgField(name="val", type_str="int32"),
            ],
        ))
        ns: dict = {}
        for src in (leaf_code, mid_code, top_code):
            kept = [line for line in src.splitlines() if not line.startswith("from ") or any(
                        line.startswith(f"from {p}") for p in ("typing", "dataclasses", "pycdr2", "zros2", "collections"))]
            exec(compile(ast.parse("\n".join(kept)), "<gen>", "exec"), ns)

        obj = ns["Top"](child=ns["Mid"](child=ns["Leaf"](val=1), val=2), val=3)
        d = obj.to_dict()
        assert d == {"child": {"child": {"val": 1}, "val": 2}, "val": 3}

        obj2 = ns["Top"].from_dict(d)
        assert obj2.val == 3
        assert obj2.child.val == 2
        assert obj2.child.child.val == 1

    def test_large_array_roundtrip(self):
        """Array with 100 elements."""
        code = generate_message_module(MsgDefinition(
            package="test", type_name="Large", type_kind="msg",
            fields=[MsgField(name="values", type_str="float64[]")],
        ))
        Cls = _exec_class(code, "Large")
        data = [float(i) for i in range(100)]
        obj = Cls(values=data)

        d = obj.to_dict()
        assert len(d["values"]) == 100
        assert d["values"][0] == 0.0
        assert d["values"][99] == 99.0

        obj2 = Cls.from_dict(d)
        assert len(obj2.values) == 100

    def test_bounded_sequence_roundtrip(self):
        """Bounded sequence (sequence<T,N>)."""
        code = generate_message_module(MsgDefinition(
            package="test", type_name="BoundedSeq", type_kind="msg",
            fields=[
                MsgField(name="vals", type_str="sequence<int32,10>"),
                MsgField(name="id", type_str="int32"),
            ],
        ))
        Cls = _exec_class(code, "BoundedSeq")
        obj = Cls(vals=[1, 2, 3], id=99)

        d = obj.to_dict()
        assert d == {"vals": [1, 2, 3], "id": 99}

        obj2 = Cls.from_dict({"vals": [4, 5], "id": 0})
        assert list(obj2.vals) == [4, 5]


# ═══════════════════════════════════════════════════════════════════════════
# from_attributes runtime correctness
# ═══════════════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════════════
# Codegen robustness
# ═══════════════════════════════════════════════════════════════════════════


class TestCodegenRobustness:
    """Verify error handling in codegen helper functions."""

    def test_is_container_type_true(self):
        """Array/sequence type strings return True."""
        from zros2.generator._codegen._msg import _is_container_type

        assert _is_container_type("int32[]") is True
        assert _is_container_type("float64[3]") is True
        assert _is_container_type("sequence<uint8>") is True
        assert _is_container_type("sequence<Point,10>") is True
        assert _is_container_type("int32[<=5]") is True

    def test_is_container_type_false(self):
        """Scalar type strings return False."""
        from zros2.generator._codegen._msg import _is_container_type

        assert _is_container_type("int32") is False
        assert _is_container_type("float64") is False
        assert _is_container_type("string") is False
        assert _is_container_type("string<=128") is False

    def test_is_container_type_malformed(self):
        """Unparseable type strings return False without crashing."""
        from zros2.generator._codegen._msg import _is_container_type

        assert _is_container_type("") is False
        assert _is_container_type("int32[") is False
        assert _is_container_type("sequence<") is False
        assert _is_container_type("!!!") is False

    def test_generate_invalid_class_name_raises(self):
        """Empty or malformed type_name raises ValueError."""
        import pytest
        from zros2.generator._codegen._msg import generate_message_module
        from zros2.generator._parser import MsgDefinition

        with pytest.raises(ValueError, match="Invalid type_name"):
            generate_message_module(MsgDefinition(
                package="test", type_name="", type_kind="msg",
            ))

        with pytest.raises(ValueError, match="Invalid type_name"):
            generate_message_module(MsgDefinition(
                package="test", type_name="/", type_kind="msg",
            ))


class TestFromAttributes:
    """Exercise ``from_attributes`` on generated message types."""

    def test_flat_message(self):
        """Object with matching attributes."""
        from tests._test_msgs import IntMsg

        obj = type("Obj", (), {"data": 42})()
        result = IntMsg.from_attributes(obj)
        assert result.data == 42

    def test_two_fields(self):
        """Object with two matching attributes."""
        from tests._test_msgs import PairMsg

        obj = type("Obj", (), {"value": 7, "label": "test"})()
        result = PairMsg.from_attributes(obj)
        assert result.value == 7
        assert result.label == "test"

    def test_missing_field_raises(self):
        """Object missing a required field raises KeyError."""
        import pytest
        from tests._test_msgs import PairMsg

        obj = type("Obj", (), {"value": 1})()
        with pytest.raises(KeyError):
            PairMsg.from_attributes(obj)

    def test_wrong_type_raises(self):
        """Object field with incompatible type raises TypeError."""
        import pytest
        from tests._test_msgs import IntMsg

        obj = type("Obj", (), {"data": "not an int"})()
        with pytest.raises(TypeError):
            IntMsg.from_attributes(obj)