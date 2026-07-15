"""Unit tests for ``zros2.generator._utilities``."""

import ast

from zros2.generator._utilities import (
    _to_snake_case,
    _default_expr,
    _format_pycdr2_imports,
    _format_external_imports,
    _generated_metadata_stmts,
)


# ======================================================================
# _to_snake_case
# ======================================================================

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
        assert _to_snake_case("GetUUID") == "get_uuid"

    def test_multi_underscore(self):
        assert (
            _to_snake_case("Foo_Bar_Baz")
            == "foo_bar_baz"
        )


# ======================================================================
# _default_expr
# ======================================================================

class TestDefaultExpr:
    def test_int_types(self):
        assert _default_expr("int32") == "0"
        assert _default_expr("uint8") == "0"
        assert _default_expr("int64") == "0"
        assert _default_expr("byte") == "0"
        assert _default_expr("char") == "0"

    def test_float_types(self):
        assert _default_expr("float32") == "0.0"
        assert _default_expr("float64") == "0.0"

    def test_string_types(self):
        assert _default_expr("string") == '""'
        assert _default_expr("wstring") == '""'

    def test_bool(self):
        assert _default_expr("bool") == "False"

    def test_array_types(self):
        assert _default_expr("int32[]") == "()"
        assert _default_expr("uint8[]") == "()"
        assert _default_expr("float64[]") == "()"

    def test_fixed_array(self):
        assert _default_expr("int32[3]") == "()"
        assert _default_expr("uint8[16]") == "(0,) * 16"

    def test_sequence(self):
        assert _default_expr("sequence<uint8>") == "()"
        assert _default_expr("sequence<int32>") == "()"
        assert _default_expr("sequence<float64>") == "()"

    def test_bounded_string(self):
        assert _default_expr("string<=255") == '""'
        assert _default_expr("string<=100") == '""'

    def test_time_and_duration(self):
        assert _default_expr("time") == "None"
        assert _default_expr("duration") == "None"

    def test_nested_type(self):
        assert _default_expr("std_msgs/msg/Header") == "None"
        assert _default_expr("geometry_msgs/Point") == "None"

    def test_unknown_type(self):
        assert _default_expr("something/weird") == "None"
        assert _default_expr("") == "None"


# ======================================================================
# _format_pycdr2_imports
# ======================================================================

class TestFormatPycdr2Imports:
    def test_empty(self):
        assert _format_pycdr2_imports(frozenset()) == ""

    def test_single_import(self):
        result = _format_pycdr2_imports(frozenset({"int32"}))
        assert result == "from pycdr2.types import int32"

    def test_two_imports(self):
        result = _format_pycdr2_imports(frozenset({"int32", "float64"}))
        assert "int32" in result
        assert "float64" in result
        assert "(" not in result  # single-line

    def test_four_imports(self):
        names = {"int32", "float64", "uint8", "string"}
        result = _format_pycdr2_imports(frozenset(names))
        assert "(" not in result
        for n in names:
            assert n in result

    def test_five_imports_multi_line(self):
        names = {"int32", "float64", "uint8", "string", "sequence"}
        result = _format_pycdr2_imports(frozenset(names))
        assert "(" in result  # multi-line
        assert ")" in result
        for n in names:
            assert n in result

    def test_many_imports_alphabetical(self):
        names = {"uint32", "int32", "float64", "uint8", "int64"}
        result = _format_pycdr2_imports(frozenset(names))
        # The function sorts alphabetically; find the import line order
        lines = result.strip().split("\n")
        # Should be multi-line (5 > 4)
        assert len(lines) > 2


# ======================================================================
# _format_external_imports
# ======================================================================

class TestFormatExternalImports:
    def test_empty(self):
        assert _format_external_imports([]) == ""

    def test_single(self):
        result = _format_external_imports(
            ["from std_msgs.msg.header import Header"]
        )
        assert result == "from std_msgs.msg.header import Header"

    def test_multiple(self):
        imports = [
            "from std_msgs.msg.header import Header",
            "from builtin_interfaces.msg.time import Time",
        ]
        result = _format_external_imports(imports)
        assert "Header" in result
        assert "Time" in result

    def test_deduplicates(self):
        imports = [
            "from std_msgs.msg.header import Header",
            "from std_msgs.msg.header import Header",
        ]
        result = _format_external_imports(imports)
        # Should only appear once
        assert result.count("Header") == 1

    def test_sorts(self):
        imports = [
            "from z_pkg.msg.zee import Zee",
            "from a_pkg.msg.aaa import Aaa",
        ]
        result = _format_external_imports(imports)
        lines = result.split("\n")
        assert lines[0].startswith("from a_pkg")  # sorted first


# ======================================================================
# _generated_metadata_stmts
# ======================================================================

class TestGeneratedMetadataStmts:
    def test_with_source(self):
        stmts = _generated_metadata_stmts("std_msgs/msg/String.msg")
        mod = ast.fix_missing_locations(ast.Module(body=stmts, type_ignores=[]))
        code = ast.unparse(mod)
        assert "__generated__ = True" in code
        assert "zros2-gen v" in code
        assert "std_msgs/msg/String.msg" in code

    def test_without_source(self):
        stmts = _generated_metadata_stmts()
        mod = ast.fix_missing_locations(ast.Module(body=stmts, type_ignores=[]))
        code = ast.unparse(mod)
        assert "__generated__ = True" in code
        assert "zros2-gen v" in code
        assert "__source__" not in code

    def test_not_annotated(self):
        """Metadata must NOT use AnnAssign, so it never leaks into
        ``__annotations__``."""
        for stmt in _generated_metadata_stmts("x.msg"):
            assert not isinstance(stmt, ast.AnnAssign)
            assert isinstance(stmt, ast.Assign)
