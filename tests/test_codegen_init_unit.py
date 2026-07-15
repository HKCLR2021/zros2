"""Component-level tests for ``zros2.generator._codegen._init``.

Tests the ``__init__.py`` code generators in isolation:
- ``generate_init_module`` — per-subdirectory init files
- ``generate_package_init`` — root package-level init files
"""

import ast
import pytest

from zros2.generator._codegen._init import (
    generate_init_module,
    generate_package_init,
)


# ======================================================================
# generate_init_module — per-subdirectory __init__.py
# ======================================================================

class TestGenerateInitModule:
    """Tests for ``msg/__init__.py``, ``srv/__init__.py``, etc."""

    def test_empty_type_names_emits_pass(self):
        result = generate_init_module("pkg", "msg", [])
        assert "pass" in result

    def test_empty_type_names_has_docstring(self):
        result = generate_init_module("pkg", "msg", [])
        assert "Auto-generated ROS 2 type index for pkg/msg" in result

    def test_metadata_present(self):
        result = generate_init_module("pkg", "msg", ["Point"])
        assert "__generated__ = True" in result
        assert "zros2-gen v" in result

    def test_metadata_no_source(self):
        """__init__.py aggregations must NOT have __source__."""
        result = generate_init_module("pkg", "msg", ["Point"])
        assert "__source__" not in result

    def test_single_type_export(self):
        result = generate_init_module("pkg", "msg", ["Point"])
        assert "from ._point import Point" in result

    def test_multiple_types_exported(self):
        result = generate_init_module("pkg", "msg", ["A", "B"])
        assert "from ._a import A" in result
        assert "from ._b import B" in result

    def test_types_sorted(self):
        result = generate_init_module("pkg", "msg", ["B", "A"])
        # Should appear in alphabetical order: A, then B
        a_idx = result.index("from ._a import A")
        b_idx = result.index("from ._b import B")
        assert a_idx < b_idx

    def test_msg_subdir_registers_types(self):
        result = generate_init_module("pkg", "msg", ["Point"])
        assert "register" in result or "_register" in result
        assert "pkg/msg/Point" in result

    def test_srv_subdir_does_not_register(self):
        result = generate_init_module("pkg", "srv", ["Foo"])
        assert "_register" not in result
        assert "from ._foo import Foo" in result

    def test_action_subdir_does_not_register(self):
        result = generate_init_module("pkg", "action", ["Bar"])
        assert "_register" not in result
        assert "from ._bar import Bar" in result

    def test_type_to_file_mapping(self):
        result = generate_init_module(
            "pkg", "srv", ["Foo_Request", "Foo_Response"],
            type_to_file={"Foo_Request": "_foo", "Foo_Response": "_foo"},
        )
        assert "from ._foo import Foo_Request" in result
        assert "from ._foo import Foo_Response" in result

    def test_root_package_in_registry_import(self):
        result = generate_init_module("pkg", "msg", ["Point"],
                                      root_package="zros2_msgs")
        assert "zros2_msgs._registry" in result

    def test_register_calls_for_each_type(self):
        result = generate_init_module("pkg", "msg", ["A", "B"])
        assert "pkg/msg/A" in result
        assert "pkg/msg/B" in result

    def test_output_syntax(self):
        result = generate_init_module("pkg", "msg", ["Point"])
        tree = ast.parse(result)
        assert tree is not None

    def test_empty_output_syntax(self):
        result = generate_init_module("pkg", "msg", [])
        tree = ast.parse(result)
        assert tree is not None


# ======================================================================
# generate_package_init — package-level __init__.py
# ======================================================================

class TestGeneratePackageInit:
    """Tests for the top-level package ``__init__.py``."""

    def test_empty_subdirs(self):
        result = generate_package_init("my_pkg", [])
        assert "Package: my_pkg" in result

    def test_single_subdir(self):
        result = generate_package_init("my_pkg", ["msg"])
        assert "from . import msg" in result
        assert "Package: my_pkg" in result

    def test_multiple_subdirs(self):
        result = generate_package_init("my_pkg", ["msg", "srv"])
        assert "from . import msg" in result
        assert "from . import srv" in result

    def test_subdirs_sorted(self):
        result = generate_package_init("my_pkg", ["srv", "msg"])
        # msg should come before srv alphabetically
        msg_idx = result.index("from . import msg")
        srv_idx = result.index("from . import srv")
        assert msg_idx < srv_idx

    def test_duplicate_subdirs_deduplicated(self):
        result = generate_package_init("my_pkg", ["msg", "msg"])
        assert result.count("from . import msg") == 1

    def test_output_syntax(self):
        result = generate_package_init("my_pkg", ["msg", "srv"])
        tree = ast.parse(result)
        assert tree is not None

    def test_empty_output_syntax(self):
        result = generate_package_init("my_pkg", [])
        tree = ast.parse(result)
        assert tree is not None

    def test_with_action_subdir(self):
        result = generate_package_init("my_pkg", ["msg", "srv", "action"])
        assert "from . import action" in result
        assert "from . import msg" in result
        assert "from . import srv" in result

    def test_metadata_present(self):
        result = generate_package_init("my_pkg", ["msg"])
        assert "__generated__ = True" in result
        assert "zros2-gen v" in result

    def test_metadata_no_source(self):
        result = generate_package_init("my_pkg", ["msg"])
        assert "__source__" not in result
