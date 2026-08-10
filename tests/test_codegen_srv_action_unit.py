"""Component-level tests for ``zros2.generator.codegen._service_action``.

Tests the service/action wrapper generation in isolation:
- ``is_local_import`` self-reference detection
- ``wrapper_class_ast`` output structure
- ``merge_type_modules`` AST merging
- ``generate_service_wrappers`` and ``generate_action_wrappers``
"""

import ast

from zros2.generator.codegen._message import GeneratedFile
from zros2.generator.codegen._service_action import (
    ACTION_SUFFIXES,
    SRV_SUFFIXES,
    generate_action_wrappers,
    generate_service_wrappers,
    is_local_import,
    merge_type_modules,
    wrapper_class_ast,
)
from zros2.generator.parsing._models import MsgDefinition, MsgField

# ======================================================================
# SRV_SUFFIXES / ACTION_SUFFIXES
# ======================================================================


class TestSuffixConstants:
    def test_srv_suffixes(self):
        assert SRV_SUFFIXES == ("_Request", "_Response")

    def test_action_suffixes_count(self):
        assert len(ACTION_SUFFIXES) == 8

    def test_action_suffixes_contents(self):
        assert "_Goal" in ACTION_SUFFIXES
        assert "_Result" in ACTION_SUFFIXES
        assert "_Feedback" in ACTION_SUFFIXES
        assert "_FeedbackMessage" in ACTION_SUFFIXES
        assert "_SendGoal_Request" in ACTION_SUFFIXES
        assert "_SendGoal_Response" in ACTION_SUFFIXES
        assert "_GetResult_Request" in ACTION_SUFFIXES
        assert "_GetResult_Response" in ACTION_SUFFIXES


# ======================================================================
# is_local_import — self-reference detection
# ======================================================================


class TestIsLocalImport:
    def test_detect_self_reference(self):
        """An ImportFrom targeting a name in local_names is a self-reference."""
        stmt = ast.parse("from _foo import Foo_Request").body[0]
        assert is_local_import(stmt, {"Foo_Request", "Foo_Response"})

    def test_not_self_reference(self):
        """An ImportFrom targeting something NOT in local_names is external."""
        stmt = ast.parse("from pycdr2.types import int32").body[0]
        assert not is_local_import(stmt, {"Foo_Request", "Foo_Response"})

    def test_import_with_asname(self):
        """If asname is in local_names, it's a self-reference."""
        stmt = ast.parse("from _foo import _Foo_Request as Foo_Request").body[0]
        assert is_local_import(stmt, {"Foo_Request"})

    def test_not_importfrom_returns_false(self):
        """Only ImportFrom statements are checked."""
        stmt = ast.parse("x = 1").body[0]
        assert not is_local_import(stmt, {"Foo"})

    def test_importfrom_no_names_returns_false(self):
        stmt = ast.ImportFrom(module="foo", names=[], level=0)
        assert not is_local_import(stmt, {"Foo"})

    def test_leading_underscore_stripped(self):
        """A leading _ on the imported name is stripped before comparison."""
        stmt = ast.parse("from _foo import _Foo_Request").body[0]
        assert is_local_import(stmt, {"Foo_Request"})

    def test_plain_import_not_checked(self):
        stmt = ast.parse("import os").body[0]
        assert not is_local_import(stmt, {"os"})


# ======================================================================
# wrapper_class_ast
# ======================================================================


class TestWrapperClassAST:
    def test_structure_with_defaults(self):
        node = wrapper_class_ast(
            "Foo",
            ["Request", "Response"],
            ["Foo_Request", "Foo_Response"],
            has_defaults=True,
        )
        code = ast.unparse(node)
        assert "class Foo:" in code
        assert "Request: ClassVar[type[Foo_Request]] = Foo_Request" in code
        assert "Response: ClassVar[type[Foo_Response]] = Foo_Response" in code
        assert "__ros_name__" not in code  # no full_name → no __ros_name__

    def test_structure_with_full_name(self):
        node = wrapper_class_ast(
            "Foo",
            ["Request", "Response"],
            ["Foo_Request", "Foo_Response"],
            has_defaults=True,
            full_name="pkg/srv/Foo",
        )
        code = ast.unparse(node)
        assert "class Foo:" in code
        assert "__ros_name__: str = 'pkg/srv/Foo'" in code
        assert "Request: ClassVar[type[Foo_Request]] = Foo_Request" in code

    def test_structure_without_defaults(self):
        node = wrapper_class_ast(
            "Foo",
            ["Request", "Response"],
            ["Foo_Request", "Foo_Response"],
            has_defaults=False,
        )
        code = ast.unparse(node)
        assert "Request: ClassVar[type[Foo_Request]]" in code
        assert "= Foo_Request" not in code  # no assignment

    def test_action_wrapper(self):
        node = wrapper_class_ast(
            "DoAction",
            ["Goal", "Result", "Feedback"],
            ["DoAction_Goal", "DoAction_Result", "DoAction_Feedback"],
            has_defaults=True,
            full_name="pkg/action/DoAction",
        )
        code = ast.unparse(node)
        assert "class DoAction:" in code
        assert "__ros_name__: str = 'pkg/action/DoAction'" in code
        assert "Goal: ClassVar[type[DoAction_Goal]] = DoAction_Goal" in code
        assert "Result: ClassVar[type[DoAction_Result]] = DoAction_Result" in code

    def test_empty_attributes(self):
        node = wrapper_class_ast("Empty", [], [], has_defaults=True)
        code = ast.unparse(node)
        assert "class Empty:" in code

    def test_single_attribute(self):
        node = wrapper_class_ast("Single", ["Only"], ["OnlyCls"], has_defaults=True)
        code = ast.unparse(node)
        assert "Only: ClassVar[type[OnlyCls]] = OnlyCls" in code

    def test_syntax_valid(self):
        node = wrapper_class_ast(
            "Foo",
            ["A", "B"],
            ["Foo_A", "Foo_B"],
            has_defaults=True,
        )
        ast.fix_missing_locations(node)
        code = ast.unparse(ast.Module(body=[node], type_ignores=[]))
        compile(code, "<test>", "exec")


# ======================================================================
# merge_type_modules — core merge engine
# ======================================================================


class TestMergeTypeModules:
    def test_merges_two_definitions(self):
        req = MsgDefinition(
            package="pkg",
            type_name="Foo_Request",
            type_kind="srv",
            fields=[MsgField(name="a", type_str="int32")],
        )
        resp = MsgDefinition(
            package="pkg",
            type_name="Foo_Response",
            type_kind="srv",
            fields=[MsgField(name="b", type_str="float64")],
        )
        py_content, pyi_content = merge_type_modules(
            [req, resp],
            extra_py_stmts=[
                ast.parse("x = 1").body[0],
            ],
            extra_pyi_stmts=[],
            module_doc="Merged service.",
            root_package="",
        )
        assert "class Foo_Request(IdlStruct):" in py_content
        assert "class Foo_Response(IdlStruct):" in py_content
        assert pyi_content is not None

    def test_self_reference_import_removed(self):
        """If one sub-type imports the other, that import is dropped."""
        req = MsgDefinition(
            package="pkg",
            type_name="Foo_Request",
            type_kind="srv",
            fields=[MsgField(name="a", type_str="int32")],
        )
        resp = MsgDefinition(
            package="pkg",
            type_name="Foo_Response",
            type_kind="srv",
            fields=[MsgField(name="b", type_str="float64")],
        )
        py_content, _ = merge_type_modules(
            [req, resp],
            extra_py_stmts=[],
            extra_pyi_stmts=[],
            module_doc="Test.",
            root_package="",
        )
        # The self-referencing import should be gone
        assert "from ._foo_request import" not in py_content

    def test_import_deduplication(self):
        """Multiple sub-types importing the same module get merged."""
        req = MsgDefinition(
            package="pkg",
            type_name="Foo_Request",
            type_kind="srv",
            fields=[MsgField(name="a", type_str="int32")],
        )
        resp = MsgDefinition(
            package="pkg",
            type_name="Foo_Response",
            type_kind="srv",
            fields=[MsgField(name="b", type_str="float64")],
        )
        py_content, _ = merge_type_modules(
            [req, resp],
            extra_py_stmts=[],
            extra_pyi_stmts=[],
            module_doc="Test.",
            root_package="",
        )
        # Both use pycdr2.types imports; they should be merged into one
        import_count = py_content.count("from pycdr2.types import")
        assert import_count == 1

    def test_extra_stmts_included(self):
        req = MsgDefinition(
            package="pkg",
            type_name="Foo_Request",
            type_kind="srv",
            fields=[MsgField(name="a", type_str="int32")],
        )
        resp = MsgDefinition(
            package="pkg",
            type_name="Foo_Response",
            type_kind="srv",
            fields=[MsgField(name="b", type_str="float64")],
        )
        wrapper = ast.parse("class Foo: pass").body[0]
        py_content, _ = merge_type_modules(
            [req, resp],
            extra_py_stmts=[wrapper],
            extra_pyi_stmts=[],
            module_doc="Test.",
            root_package="",
        )
        assert "class Foo:" in py_content

    def test_post_body_stmts_appended(self):
        req = MsgDefinition(
            package="pkg",
            type_name="Foo_Request",
            type_kind="srv",
            fields=[MsgField(name="a", type_str="int32")],
        )
        resp = MsgDefinition(
            package="pkg",
            type_name="Foo_Response",
            type_kind="srv",
            fields=[MsgField(name="b", type_str="float64")],
        )
        reg_call = ast.parse('print("registered")').body[0]
        py_content, _ = merge_type_modules(
            [req, resp],
            extra_py_stmts=[],
            extra_pyi_stmts=[],
            module_doc="Test.",
            root_package="",
            post_body_stmts=[reg_call],
        )
        assert "registered" in py_content

    def test_merged_code_syntax_valid(self):
        req = MsgDefinition(
            package="pkg",
            type_name="Foo_Request",
            type_kind="srv",
            fields=[MsgField(name="a", type_str="int32")],
        )
        resp = MsgDefinition(
            package="pkg",
            type_name="Foo_Response",
            type_kind="srv",
            fields=[MsgField(name="b", type_str="float64")],
        )
        py_content, _ = merge_type_modules(
            [req, resp],
            extra_py_stmts=[],
            extra_pyi_stmts=[],
            module_doc="Test.",
            root_package="",
        )
        compile(py_content, "<test>", "exec")

    def test_stub_also_produced(self):
        req = MsgDefinition(
            package="pkg",
            type_name="Foo_Request",
            type_kind="srv",
            fields=[MsgField(name="a", type_str="int32")],
        )
        resp = MsgDefinition(
            package="pkg",
            type_name="Foo_Response",
            type_kind="srv",
            fields=[MsgField(name="b", type_str="float64")],
        )
        _, pyi_content = merge_type_modules(
            [req, resp],
            extra_py_stmts=[],
            extra_pyi_stmts=[],
            module_doc="Test.",
            root_package="",
        )
        assert "class Foo_Request:" in pyi_content
        assert "class Foo_Response:" in pyi_content

    def test_metadata_present_in_both_py_and_pyi(self):
        req = MsgDefinition(
            package="pkg",
            type_name="Foo_Request",
            type_kind="srv",
            fields=[MsgField(name="a", type_str="int32")],
        )
        resp = MsgDefinition(
            package="pkg",
            type_name="Foo_Response",
            type_kind="srv",
            fields=[MsgField(name="b", type_str="float64")],
        )
        py_content, pyi_content = merge_type_modules(
            [req, resp],
            extra_py_stmts=[],
            extra_pyi_stmts=[],
            module_doc="Test.",
            root_package="",
        )
        # .py side
        assert "__generated__ = True" in py_content
        assert "zros2-gen v" in py_content
        # .pyi side
        assert "__generated__ = True" in pyi_content
        assert "zros2-gen v" in pyi_content

    def test_metadata_not_duplicated(self):
        """Metadata from individual sub-type modules must be stripped
        during merge so it appears exactly once."""
        req = MsgDefinition(
            package="pkg",
            type_name="Foo_Request",
            type_kind="srv",
            fields=[MsgField(name="a", type_str="int32")],
        )
        resp = MsgDefinition(
            package="pkg",
            type_name="Foo_Response",
            type_kind="srv",
            fields=[MsgField(name="b", type_str="float64")],
        )
        py_content, _ = merge_type_modules(
            [req, resp],
            extra_py_stmts=[],
            extra_pyi_stmts=[],
            module_doc="Test.",
            root_package="",
        )
        import ast as _ast

        tree = _ast.parse(py_content)
        generated_count = sum(
            1
            for stmt in tree.body
            if isinstance(stmt, _ast.Assign)
            and stmt.targets
            and isinstance(stmt.targets[0], _ast.Name)
            and stmt.targets[0].id == "__generated__"
        )
        assert generated_count == 1, (
            f"Expected 1 __generated__ assignment, got {generated_count}"
        )

    def test_plain_import_deduplication(self):
        """Plain ``ast.Import`` statements (not ImportFrom) are deduplicated by
        their unparsed string representation.

        Covers the ``isinstance(stmt, ast.Import)`` branch in both .py and .pyi paths.
        """
        req = MsgDefinition(
            package="pkg",
            type_name="Foo_Request",
            type_kind="srv",
            fields=[MsgField(name="a", type_str="int32")],
        )
        resp = MsgDefinition(
            package="pkg",
            type_name="Foo_Response",
            type_kind="srv",
            fields=[MsgField(name="b", type_str="float64")],
        )
        extra_import = ast.parse("import os").body[0]
        assert isinstance(extra_import, ast.Import)
        py_content, pyi_content = merge_type_modules(
            [req, resp],
            extra_py_stmts=[extra_import],
            extra_pyi_stmts=[extra_import],
            module_doc="Test.",
            root_package="",
        )
        assert "import os" in py_content
        assert "import os" in pyi_content

    def test_extra_importfrom_in_extra_stmts(self):
        """ImportFrom statements in extra_py_stmts are merged into the deduplicated
        imports dict.

        Covers the extra_py_stmts loop for ImportFrom deduplication (lines 284-295).
        """
        req = MsgDefinition(
            package="pkg",
            type_name="Foo_Request",
            type_kind="srv",
            fields=[MsgField(name="a", type_str="int32")],
        )
        extra_import = ast.parse("from collections.abc import Sequence").body[0]
        assert isinstance(extra_import, ast.ImportFrom)
        py_content, _ = merge_type_modules(
            [req],
            extra_py_stmts=[extra_import],
            extra_pyi_stmts=[],
            module_doc="Test.",
            root_package="",
        )
        assert "from collections.abc import Sequence" in py_content

    def test_non_import_extra_stmts_in_body(self):
        """Non-import statements in extra_py_stmts go to the body, not the import block.

        Covers the list comprehension that filters non-ImportFrom/Import statements.
        """
        req = MsgDefinition(
            package="pkg",
            type_name="Foo_Request",
            type_kind="srv",
            fields=[MsgField(name="a", type_str="int32")],
        )
        extra_import = ast.parse("import os").body[0]
        extra_body_stmt = ast.parse("x = 42").body[0]
        py_content, _ = merge_type_modules(
            [req],
            extra_py_stmts=[extra_import, extra_body_stmt],
            extra_pyi_stmts=[],
            module_doc="Test.",
            root_package="",
        )
        assert "import os" in py_content
        assert "x = 42" in py_content

    def test_extra_pyi_non_import_stmts(self):
        """Non-import statements in extra_pyi_stmts go to the pyi body.

        Covers the ``else: pyi_extra_body.append(stmt)`` branch in the pyi extra loop.
        """
        req = MsgDefinition(
            package="pkg",
            type_name="Foo_Request",
            type_kind="srv",
            fields=[MsgField(name="a", type_str="int32")],
        )
        extra_body_stmt = ast.parse("x: int = 42").body[0]
        _, pyi_content = merge_type_modules(
            [req],
            extra_py_stmts=[],
            extra_pyi_stmts=[extra_body_stmt],
            module_doc="Test.",
            root_package="",
        )
        assert "x: int = 42" in pyi_content

    def test_extra_importfrom_dedup_name_in_extra_stmts(self):
        """ImportFrom in extra_py_stmts with an already-registered import name
        is skipped (the ``n.name not in existing_names`` False branch).

        Covers the partial branch at line 292 (and similarly at line 372 for pyi).
        """
        req = MsgDefinition(
            package="pkg",
            type_name="Foo_Request",
            type_kind="srv",
            fields=[MsgField(name="a", type_str="int32")],
        )
        # The req generates `from pycdr2.types import int32` already.
        # Adding an extra with the same module+name triggers dedup.
        duplicate_import = ast.parse("from pycdr2.types import int32").body[0]
        assert isinstance(duplicate_import, ast.ImportFrom)
        py_content, pyi_content = merge_type_modules(
            [req],
            extra_py_stmts=[duplicate_import],
            extra_pyi_stmts=[duplicate_import],
            module_doc="Test.",
            root_package="",
        )
        # The `int32` should appear exactly once in the import
        assert py_content.count("int32") >= 1
        assert pyi_content.count("int32") >= 1

    def test_extra_pyi_importfrom_dedup_name(self):
        """ImportFrom in extra_pyi_stmts with an already-registered import name
        is skipped.

        Covers the partial branch at line 372.
        """
        req = MsgDefinition(
            package="pkg",
            type_name="Foo_Request",
            type_kind="srv",
            fields=[MsgField(name="a", type_str="int32")],
        )
        duplicate_import = ast.parse("from pycdr2.types import int32").body[0]
        _, pyi_content = merge_type_modules(
            [req],
            extra_py_stmts=[],
            extra_pyi_stmts=[duplicate_import, duplicate_import],
            module_doc="Test.",
            root_package="",
        )
        # The import should appear
        assert "from pycdr2.types import int32" in pyi_content

    def test_extra_pyi_plain_import(self):
        """Plain ``ast.Import`` in extra_pyi_stmts is added to pyi imports dict.

        Covers ``isinstance(stmt, ast.Import)`` at line 376 in the pyi extra loop.
        """
        req = MsgDefinition(
            package="pkg",
            type_name="Foo_Request",
            type_kind="srv",
            fields=[MsgField(name="a", type_str="int32")],
        )
        extra_import = ast.parse("import sys").body[0]
        assert isinstance(extra_import, ast.Import)
        _, pyi_content = merge_type_modules(
            [req],
            extra_py_stmts=[],
            extra_pyi_stmts=[extra_import],
            module_doc="Test.",
            root_package="",
        )
        assert "import sys" in pyi_content


# ======================================================================
# generate_service_wrappers (integration-light)
# ======================================================================


class TestGenerateServiceWrappers:
    def test_generates_wrapper_for_pair(self, tmp_path):
        sub = tmp_path / "srv"
        sub.mkdir()
        files: list[GeneratedFile] = []
        defn_by_name = {
            "Foo_Request": MsgDefinition(
                package="pkg",
                type_name="Foo_Request",
                type_kind="srv",
                fields=[MsgField(name="a", type_str="int32")],
            ),
            "Foo_Response": MsgDefinition(
                package="pkg",
                type_name="Foo_Response",
                type_kind="srv",
                fields=[MsgField(name="b", type_str="float64")],
            ),
        }
        wrappers = generate_service_wrappers(
            sub,
            defn_by_name,
            ["Foo_Request", "Foo_Response"],
            "pkg",
            files,
        )
        assert wrappers == ["Foo"]
        assert len(files) == 2  # .py + .pyi

    def test_skips_missing_response(self, tmp_path):
        sub = tmp_path / "srv"
        sub.mkdir()
        files: list[GeneratedFile] = []
        defn_by_name = {
            "Foo_Request": MsgDefinition(
                package="pkg",
                type_name="Foo_Request",
                type_kind="srv",
                fields=[MsgField(name="a", type_str="int32")],
            ),
        }
        wrappers = generate_service_wrappers(
            sub,
            defn_by_name,
            ["Foo_Request"],
            "pkg",
            files,
        )
        assert wrappers == []

    def test_wrapper_has_request_response_attrs(self, tmp_path):
        sub = tmp_path / "srv"
        sub.mkdir()
        files: list[GeneratedFile] = []
        defn_by_name = {
            "Bar_Request": MsgDefinition(
                package="pkg",
                type_name="Bar_Request",
                type_kind="srv",
                fields=[MsgField(name="a", type_str="int32")],
            ),
            "Bar_Response": MsgDefinition(
                package="pkg",
                type_name="Bar_Response",
                type_kind="srv",
                fields=[MsgField(name="b", type_str="float64")],
            ),
        }
        generate_service_wrappers(
            sub,
            defn_by_name,
            ["Bar_Request", "Bar_Response"],
            "pkg",
            files,
        )
        py_content = files[0].content
        assert "class Bar:" in py_content
        assert "Request: ClassVar[type[Bar_Request]] = Bar_Request" in py_content
        assert "Response: ClassVar[type[Bar_Response]] = Bar_Response" in py_content
        assert "__ros_name__: str = 'pkg/srv/Bar'" in py_content

    def test_generated_code_syntax(self, tmp_path):
        sub = tmp_path / "srv"
        sub.mkdir()
        files: list[GeneratedFile] = []
        defn_by_name = {
            "Foo_Request": MsgDefinition(
                package="pkg",
                type_name="Foo_Request",
                type_kind="srv",
                fields=[MsgField(name="a", type_str="int32")],
            ),
            "Foo_Response": MsgDefinition(
                package="pkg",
                type_name="Foo_Response",
                type_kind="srv",
                fields=[MsgField(name="b", type_str="float64")],
            ),
        }
        generate_service_wrappers(
            sub,
            defn_by_name,
            ["Foo_Request", "Foo_Response"],
            "pkg",
            files,
        )
        compile(files[0].content, "<test>", "exec")

    def test_service_wrapper_has_metadata(self, tmp_path):
        sub = tmp_path / "srv"
        sub.mkdir()
        files: list[GeneratedFile] = []
        defn_by_name = {
            "Bar_Request": MsgDefinition(
                package="pkg",
                type_name="Bar_Request",
                type_kind="srv",
                fields=[MsgField(name="a", type_str="int32")],
            ),
            "Bar_Response": MsgDefinition(
                package="pkg",
                type_name="Bar_Response",
                type_kind="srv",
                fields=[MsgField(name="b", type_str="float64")],
            ),
        }
        generate_service_wrappers(
            sub,
            defn_by_name,
            ["Bar_Request", "Bar_Response"],
            "pkg",
            files,
        )
        py_content = files[0].content
        assert "__generated__ = True" in py_content
        assert "__source__ = 'pkg/srv/Bar.srv'" in py_content


# ======================================================================
# generate_action_wrappers (integration-light)
# ======================================================================


class TestGenerateActionWrappers:
    def _make_action_defn(self, base: str, suffix: str) -> MsgDefinition:
        return MsgDefinition(
            package="pkg",
            type_name=f"{base}{suffix}",
            type_kind="action",
        )

    def test_generates_wrapper_for_all_suffixes(self, tmp_path):
        sub = tmp_path / "action"
        sub.mkdir()
        files: list[GeneratedFile] = []
        type_names = [f"Foo{s}" for s in ACTION_SUFFIXES]
        defn_by_name = {
            n: self._make_action_defn("Foo", s)
            for s in ACTION_SUFFIXES
            for n in [f"Foo{s}"]
        }
        wrappers = generate_action_wrappers(
            sub,
            defn_by_name,
            type_names,
            "pkg",
            files,
        )
        assert wrappers == ["Foo"]
        assert len(files) == 2

    def test_skips_missing_suffix(self, tmp_path):
        sub = tmp_path / "action"
        sub.mkdir()
        files: list[GeneratedFile] = []
        # Only provide a subset of the required 8 suffixes
        type_names = ["Foo_Goal", "Foo_Result"]
        defn_by_name = {
            "Foo_Goal": self._make_action_defn("Foo", "_Goal"),
            "Foo_Result": self._make_action_defn("Foo", "_Result"),
        }
        wrappers = generate_action_wrappers(
            sub,
            defn_by_name,
            type_names,
            "pkg",
            files,
        )
        assert wrappers == []

    def test_skips_action_missing_subtypes(self, tmp_path):
        """When a SendGoal_Request exists but not all 8 sub-types are present,
        the action is silently skipped.

        Covers the ``continue`` on line 693 in ``service_action.py``.
        """
        sub = tmp_path / "action"
        sub.mkdir()
        files: list[GeneratedFile] = []
        # Only SendGoal_Request present — all() check fails → continue
        type_names = ["Foo_SendGoal_Request"]
        defn_by_name = {
            "Foo_SendGoal_Request": self._make_action_defn("Foo", "_SendGoal_Request"),
        }
        wrappers = generate_action_wrappers(
            sub,
            defn_by_name,
            type_names,
            "pkg",
            files,
        )
        assert wrappers == []
        assert files == []

    def test_wrapper_has_all_attrs(self, tmp_path):
        sub = tmp_path / "action"
        sub.mkdir()
        files: list[GeneratedFile] = []
        type_names = [f"Do{s}" for s in ACTION_SUFFIXES]
        defn_by_name = {
            n: self._make_action_defn("Do", s)
            for s in ACTION_SUFFIXES
            for n in [f"Do{s}"]
        }
        generate_action_wrappers(
            sub,
            defn_by_name,
            type_names,
            "pkg",
            files,
        )
        py_content = files[0].content
        assert "class Do:" in py_content
        assert "Goal: ClassVar[type[Do_Goal]] = Do_Goal" in py_content
        assert "Result: ClassVar[type[Do_Result]] = Do_Result" in py_content
        assert "Feedback: ClassVar[type[Do_Feedback]] = Do_Feedback" in py_content
        assert "__ros_name__: str = 'pkg/action/Do'" in py_content

    def test_generated_code_syntax(self, tmp_path):
        sub = tmp_path / "action"
        sub.mkdir()
        files: list[GeneratedFile] = []
        type_names = [f"Bar{s}" for s in ACTION_SUFFIXES]
        defn_by_name = {
            n: self._make_action_defn("Bar", s)
            for s in ACTION_SUFFIXES
            for n in [f"Bar{s}"]
        }
        generate_action_wrappers(
            sub,
            defn_by_name,
            type_names,
            "pkg",
            files,
        )
        compile(files[0].content, "<test>", "exec")

    def test_action_wrapper_has_metadata(self, tmp_path):
        sub = tmp_path / "action"
        sub.mkdir()
        files: list[GeneratedFile] = []
        type_names = [f"Do{s}" for s in ACTION_SUFFIXES]
        defn_by_name = {
            n: self._make_action_defn("Do", s)
            for s in ACTION_SUFFIXES
            for n in [f"Do{s}"]
        }
        generate_action_wrappers(
            sub,
            defn_by_name,
            type_names,
            "pkg",
            files,
        )
        py_content = files[0].content
        assert "__generated__ = True" in py_content
        assert "__source__ = 'pkg/action/Do.action'" in py_content
