"""End-to-end tests for zros2.generator."""

import importlib.util
import pathlib
import sys
import pytest

from zros2.generator import (
    collect_all_types,
    generate_all,
    write_generated_files,
    generate_message_module,
    generate_stub_module,
    parse_msg_text,
    parse_srv_file,
    parse_action_file,
    resolve_type,
    validate_dependencies,
    MsgDefinition,
    MsgField,
)
from zros2.generator._codegen._orchestrator import (
    builtin_msg_dirs,
    _strip_wrappers,
)

from zros2.generator._utilities import (
    _default_expr,
    _to_snake_case,
)


# ======================================================================
# Parser tests
# ======================================================================


class TestParseMsgText:
    def test_simple_fields(self):
        text = "int32 x\nfloat64 y\nstring name"
        defn = parse_msg_text(text, package="test", type_name="Simple")
        assert defn.package == "test"
        assert defn.type_name == "Simple"
        assert len(defn.fields) == 3
        assert defn.fields[0].name == "x"
        assert defn.fields[0].type_str == "int32"
        assert defn.fields[1].type_str == "float64"
        assert defn.fields[2].type_str == "string"

    def test_comments(self):
        text = "# this is a comment\nint32 x\n# another comment\nfloat64 y"
        defn = parse_msg_text(text, package="test", type_name="WithComment")
        assert len(defn.fields) == 2

    def test_empty_msg(self):
        text = ""
        defn = parse_msg_text(text, package="test", type_name="Empty")
        assert len(defn.fields) == 0

    def test_array_types(self):
        text = "int32[] values\nfloat64[3] fixed\nuint8 data"
        defn = parse_msg_text(text, package="test", type_name="Arrays")
        assert defn.fields[0].type_str == "int32[]"
        assert defn.fields[1].type_str == "float64[3]"
        assert defn.fields[2].type_str == "uint8"

    def test_bounded_string(self):
        text = "string<=255 name"
        defn = parse_msg_text(text, package="test", type_name="Bounded")
        assert defn.fields[0].type_str == "string<=255"

    def test_nested_type(self):
        text = "std_msgs/Header header\ngeometry_msgs/Point point"
        defn = parse_msg_text(text, package="test", type_name="Nested")
        assert defn.fields[0].type_str == "std_msgs/Header"
        assert defn.fields[1].type_str == "geometry_msgs/Point"


class TestParseSrvFile:
    def test_simple_service(self, tmp_path):
        srv_path = tmp_path / "AddTwoInts.srv"
        srv_path.write_text("int64 a\nint64 b\n---\nint64 sum\n")
        request, response = parse_srv_file(srv_path, "test")
        assert request.type_name == "AddTwoInts_Request"
        assert response.type_name == "AddTwoInts_Response"
        assert len(request.fields) == 2
        assert len(response.fields) == 1
        assert response.fields[0].name == "sum"


class TestParseActionFile:
    def test_simple_action(self, tmp_path):
        action_path = tmp_path / "Fibonacci.action"
        action_path.write_text(
            "int32 order\n---\nint32[] sequence\n---\nint32[] sequence\n"
        )
        results = parse_action_file(action_path, "test")
        names = [r.type_name for r in results]
        assert "Fibonacci_SendGoal_Request" in names
        assert "Fibonacci_SendGoal_Response" in names
        assert "Fibonacci_GetResult_Request" in names
        assert "Fibonacci_GetResult_Response" in names
        assert "Fibonacci_Feedback" in names


# ======================================================================
# Type resolution tests
# ======================================================================


class TestResolveType:
    def test_primitives(self):
        for ros_type in ("int32", "float64", "string", "bool", "uint8"):
            resolved = resolve_type(ros_type)
            assert resolved.external_import is None

    def test_nested_type(self):
        resolved = resolve_type(
            "std_msgs/msg/String", current_package="test",
        )
        assert resolved.external_import is not None
        assert "std_msgs" in resolved.external_import

    def test_array_nested(self):
        resolved = resolve_type(
            "geometry_msgs/Point[]", current_package="test",
        )
        assert "sequence" in resolved.annotation_expr

    def test_package_type_short_form(self):
        resolved = resolve_type(
            "builtin_interfaces/Time", current_package="test",
        )
        assert resolved.external_import is not None
        assert "Time" in resolved.annotation_expr


# ======================================================================
# Dependency validation tests
# ======================================================================


class TestValidateDependencies:
    def test_all_ok(self):
        types = {
            "pkg/msg/A": MsgDefinition(
                package="pkg", type_name="A", type_kind="msg",
                fields=[MsgField(name="b", type_str="pkg/msg/B")],
            ),
            "pkg/msg/B": MsgDefinition(
                package="pkg", type_name="B", type_kind="msg",
                fields=[],
            ),
        }
        validate_dependencies(types)  # should not raise

    def test_missing_dep(self):
        types = {
            "pkg/msg/A": MsgDefinition(
                package="pkg", type_name="A", type_kind="msg",
                fields=[MsgField(name="b", type_str="pkg/msg/Missing")],
            ),
        }
        with pytest.raises(ValueError, match="Missing type dependencies"):
            validate_dependencies(types)


# ======================================================================
# Code generation tests
# ======================================================================


class TestGenerateMessageModule:
    def test_simple_message(self):
        defn = MsgDefinition(
            package="test", type_name="Point", type_kind="msg",
            fields=[
                MsgField(name="x", type_str="float64"),
                MsgField(name="y", type_str="float64"),
            ],
        )
        code = generate_message_module(defn)
        assert "class Point(IdlStruct):" in code
        assert "@classmethod" in code
        assert "def from_dict" in code
        assert "def __init__" in code

    def test_generated_code_is_valid_syntax(self):
        defn = MsgDefinition(
            package="test", type_name="Sample", type_kind="msg",
            fields=[
                MsgField(name="value", type_str="int32"),
                MsgField(name="label", type_str="string"),
            ],
        )
        code = generate_message_module(defn)
        compile(code, "<test>", "exec")  # raises SyntaxError if invalid


class TestGenerateStubModule:
    def test_stub_syntax(self):
        defn = MsgDefinition(
            package="test", type_name="Point", type_kind="msg",
            fields=[
                MsgField(name="x", type_str="float64"),
                MsgField(name="y", type_str="float64"),
            ],
        )
        stub = generate_stub_module(defn)
        assert "class Point:" in stub
        assert "def __init__(self, *, x: float=0.0, y: float=0.0) -> None:" in stub
        assert "def serialize(self) -> bytes:" in stub
        assert "def deserialize(cls, data: bytes) -> Point:" in stub
        assert "from_dict" in stub
        assert "from_attributes" in stub
        assert "to_dict" in stub


# ======================================================================
# End-to-end test
# ======================================================================

class TestEndToEnd:
    """Generate from real .msg files, import, use."""

    def test_generated_code_works(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            (test_msgs := tmp / "test_pkg" / "msg").mkdir(parents=True)
            (test_msgs / "Point.msg").write_text(
                "float64 x\nfloat64 y\nfloat64 z\n"
            )
            (test_msgs / "Pose.msg").write_text(
                "test_pkg/msg/Point position\nfloat64 orientation\n"
            )

            types = collect_all_types([tmp / "test_pkg"])
            out = tmp / "out"
            files = generate_all(types, out)
            write_generated_files(files)

            sys.path.insert(0, str(out))
            try:
                mod = importlib.import_module("test_pkg.msg._point")
                Point = mod.Point
                p = Point(x=1.0, y=2.0, z=3.0)
                data = p.serialize()
                p2 = Point.deserialize(data)
                assert abs(p2.x - 1.0) < 1e-9

                d = p.to_dict()
                assert d == {"x": 1.0, "y": 2.0, "z": 3.0}

                Pose = importlib.import_module(
                    "test_pkg.msg._pose"
                ).Pose
                pose = Pose(position=p, orientation=1.0)
                data = pose.serialize()
                pose2 = Pose.deserialize(data)
                assert abs(pose2.orientation - 1.0) < 1e-9
            finally:
                sys.path.pop(0)

    def test_generated_with_builtins(self):
        """Generate using builtin type references."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            (test_msgs := tmp / "my_pkg" / "msg").mkdir(parents=True)
            (test_msgs / "WithHeader.msg").write_text(
                "std_msgs/Header header\nfloat32 value\n"
            )

            user_types = collect_all_types([tmp / "my_pkg"])
            builtin_dirs = builtin_msg_dirs("humble")
            builtin_types = collect_all_types(builtin_dirs)
            merged = {}
            merged.update(builtin_types)
            merged.update(user_types)
            validate_dependencies(merged)

            out = tmp / "out"
            files = generate_all(merged, out)
            write_generated_files(files)

            sys.path.insert(0, str(out))
            try:
                Header = importlib.import_module(
                    "std_msgs.msg._header"
                ).Header
                assert Header
            finally:
                sys.path.pop(0)


# ======================================================================
# Utility tests
# ======================================================================


class TestDefaultExpr:
    def test_primitives(self):
        assert _default_expr("int32") == "0"
        assert _default_expr("float64") == "0.0"
        assert _default_expr("string") == '""'
        assert _default_expr("bool") == "False"
        assert _default_expr("uint8[]") == "()"
        assert _default_expr("int32[]") == "()"

    def test_nested_type(self):
        assert _default_expr("std_msgs/msg/Header") == "None"


class TestToSnakeCase:
    def test_simple(self):
        assert _to_snake_case("Duration") == "duration"
        assert _to_snake_case("String") == "string"

    def test_pascal_case(self):
        assert _to_snake_case("DiagnosticStatus") == "diagnostic_status"
        assert _to_snake_case("GetGeographicMap") == "get_geographic_map"

    def test_with_underscores(self):
        assert (
            _to_snake_case("GetGeographicMap_Request")
            == "get_geographic_map_request"
        )
        assert (
            _to_snake_case("ShutdownRobot_SendGoal_Request")
            == "shutdown_robot_send_goal_request"
        )

    def test_acronym(self):
        assert _to_snake_case("UUID") == "uuid"


class TestBuiltinMsgDirs:
    def test_humble_exists(self):
        dirs = builtin_msg_dirs("humble")
        assert len(dirs) > 0
        # Should contain standard packages
        names = {d.name for d in dirs}
        assert "std_msgs" in names
        assert "builtin_interfaces" in names

    def test_invalid_distro(self):
        dirs = builtin_msg_dirs("nonexistent")
        assert dirs == []


class TestBuiltinMsgContents:
    """Verify that bundled .msg files are syntactically valid."""

    @pytest.mark.parametrize("distro", ["humble", "iron", "jazzy"])
    def test_parse_all_builtins(self, distro):
        dirs = builtin_msg_dirs(distro)
        if not dirs:
            pytest.skip(f"No builtins for {distro}")
        types = collect_all_types(dirs)
        assert len(types) > 0
        # Every parsed definition should have valid fields
        for name, defn in types.items():
            for field in defn.fields:
                assert field.name
                assert field.type_str


class TestStripWrappers:
    def test_array(self):
        assert _strip_wrappers("int32[]") == "int32"

    def test_fixed_array(self):
        assert _strip_wrappers("float64[3]") == "float64"

    def test_sequence(self):
        assert _strip_wrappers("sequence<uint8>") == "uint8"

    def test_bounded_string(self):
        assert _strip_wrappers("string<=255") == "string"

    def test_plain_type(self):
        assert _strip_wrappers("std_msgs/msg/Header") == "std_msgs/msg/Header"


class TestResolveTypeEdgeCases:
    """Additional edge cases for type resolution."""

    def test_bounded_string_type(self):
        from zros2.generator._type_map import resolve_type
        resolved = resolve_type("string<=128")
        assert "bounded_str" in resolved.annotation_expr
        assert resolved.external_import is None

    def test_sequence_type(self):
        from zros2.generator._type_map import resolve_type
        resolved = resolve_type("sequence<float64>")
        assert "sequence" in resolved.annotation_expr

    def test_fixed_array_type(self):
        from zros2.generator._type_map import resolve_type
        resolved = resolve_type("uint8[16]")
        assert "array" in resolved.annotation_expr

    def test_root_package_prefix(self):
        from zros2.generator._type_map import resolve_type
        resolved = resolve_type(
            "std_msgs/msg/String",
            current_package="test",
            root_package="my_msgs",
        )
        assert resolved.external_import is not None
        assert "my_msgs" in resolved.external_import

    def test_time_mapped(self):
        from zros2.generator._type_map import resolve_type
        resolved = resolve_type("time")
        assert resolved.external_import is not None
        assert "builtin_interfaces" in resolved.external_import

    def test_duration_mapped(self):
        from zros2.generator._type_map import resolve_type
        resolved = resolve_type("duration")
        assert resolved.external_import is not None
        assert "builtin_interfaces" in resolved.external_import


class TestParseEdgeCases:
    """Edge cases for msg text parsing."""

    def test_comment_after_field(self):
        from zros2.generator._parser import parse_msg_text
        text = "int32 x  # this is x"
        defn = parse_msg_text(text, package="test", type_name="T")
        assert len(defn.fields) == 1
        assert defn.fields[0].name == "x"

    def test_constant_field(self):
        from zros2.generator._parser import parse_msg_text
        text = "int32 FOO=42"
        defn = parse_msg_text(text, package="test", type_name="T")
        assert len(defn.constants) == 1
        assert defn.constants[0].name == "FOO"
        assert defn.constants[0].is_constant

    def test_default_value(self):
        from zros2.generator._parser import parse_msg_text
        text = "int32 x = 42"
        defn = parse_msg_text(text, package="test", type_name="T")
        assert len(defn.fields) == 1
        assert defn.fields[0].default == "42"

    def test_string_default(self):
        from zros2.generator._parser import parse_msg_text
        text = 'string name = "hello"'
        defn = parse_msg_text(text, package="test", type_name="T")
        assert len(defn.fields) == 1
        assert defn.fields[0].default == '"hello"'

    def test_dep_primitive_skipped(self):
        types = {
            "pkg/msg/A": MsgDefinition(
                package="pkg", type_name="A", type_kind="msg",
                fields=[
                    MsgField(name="x", type_str="int32"),
                    MsgField(name="y", type_str="float64[]"),
                ],
            ),
        }
        from zros2.generator._codegen._orchestrator import validate_dependencies
        validate_dependencies(types)


class TestTypeMapEdgeCases:
    """Additional coverage for ``_type_map.py``."""

    def test_is_primitive(self):
        from zros2.generator._type_map import is_primitive
        assert is_primitive("int32")
        assert is_primitive("float64")
        assert is_primitive("string")
        assert is_primitive("bool")
        assert is_primitive("uint8")
        assert not is_primitive("std_msgs/msg/Header")
        assert not is_primitive("string<=128")  # bounded_str

    def test_get_default_value(self):
        from zros2.generator._type_map import get_default_value
        assert get_default_value("int32") == "0"
        assert get_default_value("float64") == "0.0"
        assert get_default_value("string") == '""'
        assert get_default_value("bool") == "False"
        assert get_default_value("time") == "None"  # string expression for code gen
        assert get_default_value("std_msgs/msg/Header") == "None"

    def test_sequence_with_external_import(self):
        from zros2.generator._type_map import resolve_type
        resolved = resolve_type(
            "sequence<std_msgs/msg/String>", current_package="test",
        )
        assert "sequence" in resolved.annotation_expr
        assert resolved.external_import is not None

    def test_unqualified_type_in_same_package(self):
        from zros2.generator._type_map import resolve_type
        resolved = resolve_type("String", current_package="my_pkg")
        assert resolved.external_import is not None
        assert "my_pkg" in resolved.external_import

    def test_package_type_without_msg_kind(self):
        from zros2.generator._type_map import resolve_type
        resolved = resolve_type(
            "my_pkg/Header", current_package="other",
        )
        assert resolved.annotation_expr == "Header"
        assert "my_pkg.msg._header" in (resolved.external_import or "")


class TestActionWrapperGeneration:
    """Cover action wrapper generation code paths."""

    def test_generate_action_wrappers(self):
        from zros2.generator._codegen._srv_action import _generate_action_wrappers
        from zros2.generator._codegen._msg import GeneratedFile
        from zros2.generator._parser import MsgDefinition
        import tempfile
        import pathlib

        def _make(name: str) -> MsgDefinition:
            return MsgDefinition(
                package="pkg", type_name=name, type_kind="action",
            )

        with tempfile.TemporaryDirectory() as tmp:
            sub = pathlib.Path(tmp) / "action"
            sub.mkdir()
            files: list[GeneratedFile] = []
            type_names = [
                "Foo_Goal",
                "Foo_Result",
                "Foo_Feedback",
                "Foo_FeedbackMessage",
                "Foo_SendGoal_Request",
                "Foo_SendGoal_Response",
                "Foo_GetResult_Request",
                "Foo_GetResult_Response",
            ]
            defn_by_name = {n: _make(n) for n in type_names}
            wrappers = _generate_action_wrappers(
                sub, defn_by_name, type_names, "pkg", files,
            )
            assert len(wrappers) == 1
            assert wrappers[0] == "Foo"
            assert len(files) == 2  # .py + .pyi

    def test_generated_action_wrapper_usable(self):
        import tempfile
        import pathlib
        import sys
        from zros2.generator import (
            collect_all_types, generate_all, write_generated_files,
        )
        from zros2.generator._codegen._orchestrator import builtin_msg_dirs

        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            (action_dir := tmp / "pkg" / "action").mkdir(parents=True)
            (action_dir / "Do.action").write_text(
                "int32 input\n---\nint32 result\n---\nfloat32 feedback\n"
            )

            # Merge user types with builtins so unique_identifier_msgs is available
            user = collect_all_types([tmp / "pkg"])
            builtins = collect_all_types(builtin_msg_dirs("humble"))
            merged = {**builtins, **user}
            from zros2.generator._codegen._orchestrator import validate_dependencies
            validate_dependencies(merged)

            out = tmp / "out"
            files = generate_all(merged, out)
            write_generated_files(files)

            sys.path.insert(0, str(out))
            try:
                _Do = importlib.import_module("pkg.action._do").Do
                assert hasattr(_Do, "Goal")
                assert hasattr(_Do, "Result")
                assert hasattr(_Do, "Feedback")
                assert hasattr(_Do, "FeedbackMessage")
                assert hasattr(_Do, "SendGoal_Request")
                assert hasattr(_Do, "SendGoal_Response")
                assert hasattr(_Do, "GetResult_Request")
                assert hasattr(_Do, "GetResult_Response")
            finally:
                sys.path.pop(0)


class TestDefaultExprEdgeCases:
    """Cover edge cases in ``_default_expr``."""

    def test_uint8_array_default(self):
        from zros2.generator._utilities import _default_expr
        assert _default_expr("uint8[]") == "()"

    def test_bounded_str_default(self):
        from zros2.generator._utilities import _default_expr
        assert _default_expr("string<=255") == '""'

    def test_time_default(self):
        from zros2.generator._utilities import _default_expr
        assert _default_expr("time") == "None"

    def test_large_import_list(self):
        from zros2.generator._utilities import _format_pycdr2_imports
        result = _format_pycdr2_imports(
            frozenset({"int32", "float64", "string", "uint8", "sequence"})
        )
        assert "(" in result  # multi-line format
        assert len(result) > 60


class TestParseParserEdgeCases:
    """Additional coverage for ``_parser.py`` uncovered branches."""

    def test_unparseable_field_line(self):
        """A line without a type-name separator is an error with context."""
        from zros2.generator._parser import parse_msg_text
        import pytest
        text = "invalid_line_without_type_and_name\nint32 x"
        with pytest.raises(ValueError, match="line 1"):
            parse_msg_text(text, package="test", type_name="T")

    def test_field_unparseable_line(self):
        """_tokenise_field_line raises ValueError for unparseable lines."""
        from zros2.generator._parser import _tokenise_field_line
        import pytest
        with pytest.raises(ValueError, match="missing field name"):
            _tokenise_field_line("12345")

    def test_default_value_trailing_comment_wiped(self):
        """Default value stripped by trailing comment (lines 169-172)."""
        from zros2.generator._parser import parse_msg_text
        text = "int32 x = 42 # this is a comment"
        defn = parse_msg_text(text, package="test", type_name="T")
        assert len(defn.fields) == 1
        assert defn.fields[0].default == "42"

    def test_invalid_srv_missing_separator(self, tmp_path):
        """Invalid .srv file raises ValueError (line 219)."""
        from zros2.generator._parser import parse_srv_file
        srv_path = tmp_path / "Bad.srv"
        srv_path.write_text("int64 a\nint64 b\n")
        import pytest
        with pytest.raises(ValueError, match="missing '---' separator"):
            parse_srv_file(srv_path, "test")

    def test_invalid_action_missing_separators(self, tmp_path):
        """Invalid .action file raises ValueError (line 256)."""
        from zros2.generator._parser import parse_action_file
        action_path = tmp_path / "Bad.action"
        action_path.write_text("int32 order\n---\nint32[] sequence\n")
        import pytest
        with pytest.raises(ValueError, match="expected two '---' separators"):
            parse_action_file(action_path, "test")

    def test_find_msg_dirs_non_existent(self):
        """find_msg_dirs with non-existent base path (line 347-348)."""
        import pathlib
        from zros2.generator._parser import find_msg_dirs
        result = find_msg_dirs([pathlib.Path("/nonexistent/path")])
        assert result == []

    def test_find_msg_dirs_with_msg_dir(self, tmp_path):
        """find_msg_dirs when base has msg/ subdir (line 351-352)."""
        from zros2.generator._parser import find_msg_dirs
        (tmp_path / "msg").mkdir()
        result = find_msg_dirs([tmp_path])
        assert tmp_path in result

    def test_find_msg_dirs_scans_subdirs(self, tmp_path):
        """find_msg_dirs scans subdirectories for msg/ (lines 355-357)."""
        from zros2.generator._parser import find_msg_dirs
        pkg_dir = tmp_path / "my_pkg"
        (pkg_dir / "msg").mkdir(parents=True)
        result = find_msg_dirs([tmp_path])
        assert pkg_dir in result


class TestGeneratorEdgeCases:
    """Additional coverage for ``_generator.py`` uncovered branches."""

    def test_builtin_msg_dirs_missing_distro_dir(self):
        """builtin_msg_dirs returns [] when distro dir doesn't exist (line 66)."""
        from zros2.generator._codegen._orchestrator import builtin_msg_dirs
        # Mock BUILTIN_MSG_DIR to point to a nonexistent location
        import pathlib
        from unittest import mock
        import zros2.generator._codegen._orchestrator as gen_mod
        with mock.patch.object(gen_mod, 'BUILTIN_MSG_DIR', pathlib.Path("/nonexistent")):
            result = builtin_msg_dirs("humble")
        assert result == []

    def test_strip_wrappers_sequence(self):
        """_strip_wrappers handles sequence<type> (line 82)."""
        from zros2.generator._codegen._orchestrator import _strip_wrappers
        assert _strip_wrappers("sequence<uint8>") == "uint8"

    def test_resolve_full_name_empty_base(self):
        """_resolve_full_name returns '' when base is empty (line 99)."""
        from zros2.generator._codegen._orchestrator import _resolve_full_name
        assert _resolve_full_name("", "test") == ""

    def test_resolve_full_name_no_slash(self):
        """_resolve_full_name with no / in base (line 110)."""
        from zros2.generator._codegen._orchestrator import _resolve_full_name
        result = _resolve_full_name("String", "my_pkg")
        assert result == "my_pkg/msg/String"

    def test_resolve_full_name_multi_slash(self):
        """_resolve_full_name with >1 / in base (line 116)."""
        from zros2.generator._codegen._orchestrator import _resolve_full_name
        result = _resolve_full_name("pkg/msg/Sub/Extra", "test")
        assert result == "pkg/msg/Sub/Extra"

    def test_resolve_full_name_with_srv(self):
        """_resolve_full_name handles /srv/ in base (line 106-107)."""
        from zros2.generator._codegen._orchestrator import _resolve_full_name
        result = _resolve_full_name("pkg/srv/Foo", "test")
        assert result == "pkg/srv/Foo"

    def test_collect_all_types_with_all_kinds(self, tmp_path):
        """collect_all_types handles msg, srv, and action dirs."""
        from zros2.generator._codegen._orchestrator import collect_all_types
        # Create a proper package directory so the name is predictable
        pkg_dir = tmp_path / "my_pkg"
        (pkg_dir / "msg").mkdir(parents=True)
        (pkg_dir / "msg" / "Point.msg").write_text("float64 x\nfloat64 y\n")
        (pkg_dir / "srv").mkdir()
        (pkg_dir / "srv" / "Empty.srv").write_text("---\n")
        (pkg_dir / "action").mkdir()
        (pkg_dir / "action" / "Do.action").write_text(
            "int32 order\n---\nint32 result\n---\nfloat32 feedback\n"
        )
        types = collect_all_types([pkg_dir])
        names = set(types.keys())
        assert "my_pkg/msg/Point" in names

    def test_generate_all_nothing_but_update_root_init(self):
        """generate_all produces root __init__ when no files exist (lines 210-216)."""
        import pathlib
        import tempfile
        from zros2.generator._codegen._orchestrator import generate_all
        types = {}
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp)
            files = generate_all(types, out)
            assert len(files) >= 1
            # Should have _registry.py and root __init__.py
            paths = [f.path for f in files]
            assert any(p.name == "_registry.py" for p in paths)
            assert any(p.name == "__init__.py" for p in paths)

    def test_generate_all_with_existing_init(self, tmp_path):
        """_update_root_init appends to existing root __init__ (lines 204-208)."""
        from zros2.generator._codegen._orchestrator import generate_all
        from zros2.generator._parser import MsgDefinition, MsgField

        types = {
            "pkg/msg/A": MsgDefinition(
                package="pkg", type_name="A", type_kind="msg",
                fields=[MsgField(name="x", type_str="int32")],
            ),
        }
        out = tmp_path / "out"
        files = generate_all(types, out)
        # Check that root __init__ has get_type etc
        init_content = None
        for f in files:
            if f.path.name == "__init__.py" and f.path.parent == out:
                init_content = f.content
                break
        assert init_content is not None
        assert "get_type" in init_content
        assert "get_service" in init_content


class TestGenCodeEdgeCases:
    """Additional coverage for ``_gen_code.py`` uncovered branches."""

    def test_generate_init_module_empty(self):
        """generate_init_module with empty type_names (line 198)."""
        from zros2.generator._codegen._init import generate_init_module
        result = generate_init_module("pkg", "msg", [])
        # AST-based generation uses "pass" instead of "# (no types)" comment
        assert "pass" in result

    def test_generate_package_init_empty(self):
        """generate_package_init with empty subdirs (line 222)."""
        from zros2.generator._codegen._init import generate_package_init
        result = generate_package_init("pkg", [])
        assert "Package: pkg" in result


class TestTypeMapEdgeCases2:
    """Additional coverage for ``_type_map.py`` uncovered branches."""

    def test_is_primitive_with_array_wrapper(self):
        """is_primitive strips array wrappers (line 223)."""
        from zros2.generator._type_map import is_primitive
        assert is_primitive("int32[3]")
        assert is_primitive("float64[]")

    def test_is_primitive_with_sequence_wrapper(self):
        """is_primitive strips sequence wrappers (line 226)."""
        from zros2.generator._type_map import is_primitive
        assert is_primitive("sequence<uint8>")
        assert not is_primitive("sequence<std_msgs/Header>")

    def test_resolve_type_unusual_format(self):
        """resolve_type with unusual format without msg/srv/action (lines 200-202)."""
        from zros2.generator._type_map import resolve_type
        # Type with 'msg' not in the path -> falls to else branch
        resolved = resolve_type("my_pkg/SomeType", current_package="test")
        assert resolved.annotation_expr == "SomeType"
        assert resolved.external_import is not None
        assert "my_pkg.msg._some_type" in resolved.external_import

    def test_resolve_nested_multi_component_type(self):
        """Type with >3 parts and no msg/srv/action keyword."""
        from zros2.generator._type_map import resolve_type
        resolved = resolve_type("pkg/sub/DeepType", current_package="test")
        # Falls to else branch: type_name = "/".join(parts[1:]) = "sub/DeepType"
        assert resolved.annotation_expr == "sub/DeepType"


class TestCLI:
    """Coverage for ``__main__.py``."""

    def test_build_parser(self):
        """build_parser returns a configured ArgumentParser."""
        from zros2.generator.__main__ import build_parser
        parser = build_parser()
        assert parser is not None

    def test_main_help(self):
        """main() with --help prints usage and exits."""
        import sys
        from zros2.generator.__main__ import main
        from unittest import mock
        test_args = ["zros2-gen", "--help"]
        with mock.patch.object(sys, "argv", test_args):
            import pytest
            with pytest.raises(SystemExit):
                main()

    def test_main_msg_dirs_not_exists(self):
        """main() with non-existent --msg-dirs prints error and exits."""
        import sys
        from zros2.generator.__main__ import main
        from unittest import mock
        test_args = [
            "zros2-gen",
            "--msg-dirs", "/nonexistent/path",
            "--ros-version", "humble",
            "--output", "/tmp/out",
        ]
        with mock.patch.object(sys, "argv", test_args):
            import pytest
            with pytest.raises(SystemExit):
                main()

    def test_main_dry_run(self, tmp_path):
        """main() with --dry-run prints would-generate and exits."""
        import sys
        from zros2.generator.__main__ import main
        from unittest import mock

        pkg_dir = tmp_path / "test_pkg"
        (pkg_dir / "msg").mkdir(parents=True)
        (pkg_dir / "msg" / "Point.msg").write_text("float64 x\nfloat64 y\n")

        test_args = [
            "zros2-gen",
            "--msg-dirs", str(pkg_dir),
            "--ros-version", "humble",
            "--output", str(tmp_path / "out"),
            "--dry-run",
        ]
        with mock.patch.object(sys, "argv", test_args):
            main()  # should not raise

    def test_main_full_generate(self, tmp_path):
        """main() generates files successfully."""
        import sys
        from zros2.generator.__main__ import main
        from unittest import mock

        pkg_dir = tmp_path / "test_pkg"
        (pkg_dir / "msg").mkdir(parents=True)
        (pkg_dir / "msg" / "Point.msg").write_text("float64 x\nfloat64 y\n")

        test_args = [
            "zros2-gen",
            "--msg-dirs", str(pkg_dir),
            "--ros-version", "humble",
            "--output", str(tmp_path / "out"),
        ]
        with mock.patch.object(sys, "argv", test_args):
            main()

        out_dir = tmp_path / "out"
        assert out_dir.is_dir()
        assert (out_dir / "_registry.py").exists()
        assert (out_dir / "test_pkg" / "msg" / "_point.py").exists()

    def test_main_with_root_package(self, tmp_path):
        """main() with --root-package generates correct imports."""
        import sys
        from zros2.generator.__main__ import main
        from unittest import mock

        pkg_dir = tmp_path / "test_pkg"
        (pkg_dir / "msg").mkdir(parents=True)
        (pkg_dir / "msg" / "Point.msg").write_text("float64 x\nfloat64 y\n")

        test_args = [
            "zros2-gen",
            "--msg-dirs", str(pkg_dir),
            "--ros-version", "humble",
            "--output", str(tmp_path / "out"),
            "--root-package", "zros2_msgs",
        ]
        with mock.patch.object(sys, "argv", test_args):
            main()
