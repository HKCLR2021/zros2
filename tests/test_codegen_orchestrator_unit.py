"""Component-level tests for ``zros2.generator._codegen._orchestrator``.

Tests the generator orchestrator in isolation:
- ``builtin_msg_dirs`` discovery
- ``_strip_wrappers`` and ``_resolve_full_name`` helpers
- ``validate_dependencies``
- ``collect_all_types`` directory scanning
- ``generate_all`` file output
- ``write_generated_files`` disk I/O
"""

import pathlib
import sys
import ast
import pytest
from unittest import mock

from zros2.generator._codegen._orchestrator import (
    BUILTIN_MSG_DIR,
    VALID_DISTROS,
    builtin_msg_dirs,
    _strip_wrappers,
    _resolve_full_name,
    validate_dependencies,
    collect_all_types,
    generate_all,
    write_generated_files,
)
from zros2.generator._codegen._msg import GeneratedFile
from zros2.generator._parser import MsgDefinition, MsgField


# ======================================================================
# BUILTIN_MSG_DIR / VALID_DISTROS
# ======================================================================

class TestConstants:
    def test_builtin_msg_dir_exists(self):
        assert BUILTIN_MSG_DIR.is_dir()

    def test_valid_distros(self):
        assert "humble" in VALID_DISTROS
        assert "iron" in VALID_DISTROS
        assert "jazzy" in VALID_DISTROS
        assert "kilted" in VALID_DISTROS
        assert "lyrical" in VALID_DISTROS


# ======================================================================
# builtin_msg_dirs
# ======================================================================

class TestBuiltinMsgDirs:
    def test_valid_distro_returns_dirs(self):
        dirs = builtin_msg_dirs("humble")
        assert len(dirs) > 0
        names = {d.name for d in dirs}
        assert "std_msgs" in names
        assert "builtin_interfaces" in names

    def test_invalid_distro_returns_empty(self):
        assert builtin_msg_dirs("nonexistent") == []

    def test_humble_and_iron_both_exist(self):
        humble = builtin_msg_dirs("humble")
        iron = builtin_msg_dirs("iron")
        assert len(humble) > 0
        assert len(iron) > 0

    def test_missing_builtin_dir(self):
        """When BUILTIN_MSG_DIR doesn't exist, returns empty."""
        with mock.patch(
            "zros2.generator._codegen._orchestrator.BUILTIN_MSG_DIR",
            pathlib.Path("/nonexistent"),
        ):
            result = builtin_msg_dirs("humble")
            assert result == []


# ======================================================================
# _strip_wrappers
# ======================================================================

class TestStripWrappers:
    def test_unbounded_array(self):
        assert _strip_wrappers("int32[]") == "int32"

    def test_fixed_array(self):
        assert _strip_wrappers("float64[3]") == "float64"

    def test_bounded_dynamic_array(self):
        """The regex currently does not handle ``[<=N]``, just ``[N]``."""
        # This is a known limitation — test the actual behaviour
        result = _strip_wrappers("int32[<=5]")
        # The regex for [N] won't match, so it falls through to raw
        assert result == "int32[<=5]"

    def test_sequence(self):
        assert _strip_wrappers("sequence<uint8>") == "uint8"

    def test_sequence_bounded(self):
        assert _strip_wrappers("sequence<uint8,10>") == "uint8"

    def test_bounded_string(self):
        assert _strip_wrappers("string<=255") == "string"

    def test_plain_type(self):
        assert _strip_wrappers("std_msgs/msg/Header") == "std_msgs/msg/Header"

    def test_empty_string(self):
        assert _strip_wrappers("") == ""

    def test_primitive_no_wrapper(self):
        assert _strip_wrappers("int32") == "int32"


# ======================================================================
# _resolve_full_name
# ======================================================================

class TestResolveFullName:
    def test_primitive_returns_empty(self):
        assert _resolve_full_name("int32", "test") == ""
        assert _resolve_full_name("string", "test") == ""

    def test_time_returns_empty(self):
        assert _resolve_full_name("time", "test") == ""
        assert _resolve_full_name("duration", "test") == ""

    def test_fully_qualified_three_part(self):
        result = _resolve_full_name("std_msgs/msg/String", "test")
        assert result == "std_msgs/msg/String"

    def test_fully_qualified_srv(self):
        result = _resolve_full_name("pkg/srv/Foo", "test")
        assert result == "pkg/srv/Foo"

    def test_fully_qualified_action(self):
        result = _resolve_full_name("pkg/action/Bar", "test")
        assert result == "pkg/action/Bar"

    def test_unqualified_adds_current_package(self):
        result = _resolve_full_name("String", "my_pkg")
        assert result == "my_pkg/msg/String"

    def test_two_parts_normalises_to_msg(self):
        result = _resolve_full_name("pkg/Foo", "test")
        assert result == "pkg/msg/Foo"

    def test_empty_string_returns_empty(self):
        assert _resolve_full_name("", "test") == ""

    def test_array_of_nested_type(self):
        """Array wrappers around nested types are stripped before resolution."""
        result2 = _resolve_full_name("std_msgs/msg/String[3]", "test")
        assert result2 == "std_msgs/msg/String"
        result3 = _resolve_full_name("std_msgs/msg/String[]", "test")
        assert result3 == "std_msgs/msg/String"

    def test_multi_slash_returns_as_is(self):
        """A type with >1 slash and no msg/srv/action returns as-is."""
        result = _resolve_full_name("a/b/c/d", "test")
        assert result == "a/b/c/d"


# ======================================================================
# validate_dependencies
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
        validate_dependencies(types)

    def test_missing_dependency_raises(self):
        types = {
            "pkg/msg/A": MsgDefinition(
                package="pkg", type_name="A", type_kind="msg",
                fields=[MsgField(name="x", type_str="pkg/msg/Missing")],
            ),
        }
        with pytest.raises(ValueError, match="Missing type dependencies"):
            validate_dependencies(types)

    def test_primitives_not_checked(self):
        types = {
            "pkg/msg/A": MsgDefinition(
                package="pkg", type_name="A", type_kind="msg",
                fields=[
                    MsgField(name="x", type_str="int32"),
                    MsgField(name="y", type_str="float64[]"),
                    MsgField(name="z", type_str="string<=255"),
                ],
            ),
        }
        validate_dependencies(types)

    def test_self_reference_not_flagged(self):
        types = {
            "pkg/msg/A": MsgDefinition(
                package="pkg", type_name="A", type_kind="msg",
                fields=[MsgField(name="self", type_str="pkg/msg/A")],
            ),
        }
        validate_dependencies(types)

    def test_empty_types_ok(self):
        validate_dependencies({})

    def test_error_message_contains_details(self):
        types = {
            "pkg/msg/A": MsgDefinition(
                package="pkg", type_name="A", type_kind="msg",
                fields=[MsgField(name="x", type_str="pkg/msg/Missing")],
            ),
        }
        with pytest.raises(ValueError) as exc:
            validate_dependencies(types)
        assert "pkg/msg/A" in str(exc.value)
        assert "pkg/msg/Missing" in str(exc.value)


# ======================================================================
# collect_all_types
# ======================================================================

class TestCollectAllTypes:
    def test_collects_msg_files(self, tmp_path):
        pkg = tmp_path / "my_pkg"
        (pkg / "msg").mkdir(parents=True)
        (pkg / "msg" / "Point.msg").write_text("float64 x\nfloat64 y\n")
        types = collect_all_types([pkg])
        assert "my_pkg/msg/Point" in types
        assert len(types["my_pkg/msg/Point"].fields) == 2

    def test_collects_srv_files(self, tmp_path):
        pkg = tmp_path / "my_pkg"
        (pkg / "srv").mkdir(parents=True)
        (pkg / "srv" / "Foo.srv").write_text("int32 a\n---\nfloat64 b\n")
        types = collect_all_types([pkg])
        assert "my_pkg/srv/Foo_Request" in types
        assert "my_pkg/srv/Foo_Response" in types

    def test_collects_action_files(self, tmp_path):
        pkg = tmp_path / "my_pkg"
        (pkg / "action").mkdir(parents=True)
        (pkg / "action" / "Do.action").write_text(
            "int32 input\n---\nint32 result\n---\nfloat32 feedback\n"
        )
        types = collect_all_types([pkg])
        action_keys = [k for k in types if "action" in k]
        # parse_action_file returns 8 sub-types
        assert len(action_keys) == 8

    def test_skips_non_existent_dirs(self, tmp_path):
        pkg = tmp_path / "my_pkg"
        # No msg/srv/action dirs created
        pkg.mkdir()
        types = collect_all_types([pkg])
        assert len(types) == 0

    def test_handles_multiple_packages(self, tmp_path):
        pkg_a = tmp_path / "pkg_a"
        pkg_b = tmp_path / "pkg_b"
        for p in [pkg_a, pkg_b]:
            (p / "msg").mkdir(parents=True)
            (p / "msg" / "Point.msg").write_text("float64 x\n")
        types = collect_all_types([pkg_a, pkg_b])
        assert "pkg_a/msg/Point" in types
        assert "pkg_b/msg/Point" in types


# ======================================================================
# generate_all
# ======================================================================

class TestGenerateAll:
    def test_empty_types_produces_registry_and_init(self):
        files = generate_all({}, pathlib.Path("/out"))
        paths = {f.path for f in files}
        assert any("_registry.py" in str(p) for p in paths)
        assert any("__init__.py" in str(p) for p in paths)

    def test_simple_message_generates_files(self):
        types = {
            "pkg/msg/Point": MsgDefinition(
                package="pkg", type_name="Point", type_kind="msg",
                fields=[MsgField(name="x", type_str="float64")],
            ),
        }
        files = generate_all(types, pathlib.Path("/out"))
        # Should include: pkg/__init__.py, pkg/msg/__init__.py,
        # pkg/msg/_point.py, pkg/msg/_point.pyi, _registry.py, root __init__.py
        py_files = [f for f in files if f.path.name.endswith(".py")]
        pyi_files = [f for f in files if f.path.name.endswith(".pyi")]
        assert len(py_files) >= 4  # _point.py, msg/__init__.py, pkg/__init__.py, root __init__.py
        assert len(pyi_files) >= 1  # _point.pyi

    def test_root_init_has_registry_imports(self):
        types = {
            "pkg/msg/A": MsgDefinition(
                package="pkg", type_name="A", type_kind="msg",
                fields=[MsgField(name="x", type_str="int32")],
            ),
        }
        files = generate_all(types, pathlib.Path("/out"))
        root_init = next(f for f in files
                         if f.path.name == "__init__.py"
                         and f.path.parent == pathlib.Path("/out"))
        assert "get_type" in root_init.content
        assert "has_type" in root_init.content
        assert "iter_types" in root_init.content
        assert "get_service" in root_init.content
        assert "get_action" in root_init.content

    def test_generated_files_syntax(self):
        types = {
            "pkg/msg/A": MsgDefinition(
                package="pkg", type_name="A", type_kind="msg",
                fields=[MsgField(name="x", type_str="int32")],
            ),
        }
        files = generate_all(types, pathlib.Path("/out"))
        for f in files:
            if f.path.suffix == ".py":
                compile(f.content, f.path.name, "exec")

    def test_root_package_affects_imports(self):
        types = {
            "pkg/msg/A": MsgDefinition(
                package="pkg", type_name="A", type_kind="msg",
                fields=[MsgField(name="x", type_str="std_msgs/msg/String")],
            ),
        }
        files = generate_all(types, pathlib.Path("/out"), root_package="zros2_msgs")
        msg_file = next(f for f in files if f.path.name == "_a.py")
        assert "zros2_msgs" in msg_file.content

    def test_registry_has_metadata(self):
        types = {}
        files = generate_all(types, pathlib.Path("/out"))
        reg_file = next(f for f in files if f.path.name == "_registry.py")
        assert "__generated__ = True" in reg_file.content
        assert "__source__" not in reg_file.content

    def test_root_init_has_metadata(self):
        types = {}
        files = generate_all(types, pathlib.Path("/out"))
        root_init = next(f for f in files
                         if f.path.name == "__init__.py"
                         and f.path.parent == pathlib.Path("/out"))
        assert "__generated__ = True" in root_init.content
        assert "__source__" not in root_init.content


# ======================================================================
# write_generated_files
# ======================================================================

class TestWriteGeneratedFiles:
    def test_writes_files_to_disk(self, tmp_path):
        files = [
            GeneratedFile(path=tmp_path / "a.py", content="x = 1\n"),
            GeneratedFile(path=tmp_path / "sub" / "b.py", content="y = 2\n"),
        ]
        written = write_generated_files(files)
        assert len(written) == 2
        assert (tmp_path / "a.py").exists()
        assert (tmp_path / "sub" / "b.py").exists()
        assert (tmp_path / "a.py").read_text() == "x = 1\n"

    def test_creates_parent_directories(self, tmp_path):
        files = [
            GeneratedFile(path=tmp_path / "a" / "b" / "c.py", content="z = 3\n"),
        ]
        write_generated_files(files)
        assert (tmp_path / "a" / "b" / "c.py").exists()

    def test_returns_written_paths(self, tmp_path):
        files = [GeneratedFile(path=tmp_path / "x.py", content="")]
        written = write_generated_files(files)
        assert written == [tmp_path / "x.py"]

    def test_empty_file_list(self, tmp_path):
        written = write_generated_files([])
        assert written == []
