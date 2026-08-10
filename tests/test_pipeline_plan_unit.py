"""Unit tests for the generator planning pipeline."""

import pathlib

import pytest

from zros2.generator.pipeline._plan import GenerationPlan, build_plan, execute_plan


class TestBuildPlan:
    def test_builds_validated_plan_with_builtins(self, tmp_path: pathlib.Path):
        """build_plan should load builtins and default root_package."""
        output = tmp_path / "zros2_msgs"
        plan = build_plan(
            user_dirs=[],
            output_dir=output,
            distro="humble",
            root_package=None,
        )
        assert isinstance(plan, GenerationPlan)
        assert plan.distro == "humble"
        assert plan.root_package == "zros2_msgs"
        assert plan.builtin_count > 0
        assert plan.user_type_names == ()
        assert plan.types

    def test_user_types_override_is_reflected_in_names(self, tmp_path: pathlib.Path):
        """User package types should appear in user_type_names."""
        pkg = tmp_path / "demo_msgs"
        msg_dir = pkg / "msg"
        msg_dir.mkdir(parents=True)
        (msg_dir / "Hello.msg").write_text("string data\n", encoding="utf-8")

        plan = build_plan(
            user_dirs=[pkg],
            output_dir=tmp_path / "out",
            distro="humble",
            root_package="out",
        )
        assert "demo_msgs/msg/Hello" in plan.user_type_names
        assert "demo_msgs/msg/Hello" in plan.types

    def test_missing_dependency_raises(self, tmp_path: pathlib.Path):
        """Unresolved nested types should raise ValueError."""
        pkg = tmp_path / "broken_msgs"
        msg_dir = pkg / "msg"
        msg_dir.mkdir(parents=True)
        (msg_dir / "Broken.msg").write_text("MissingType value\n", encoding="utf-8")

        with pytest.raises(ValueError, match="Missing type dependencies"):
            build_plan(
                user_dirs=[pkg],
                output_dir=tmp_path / "out",
                distro="humble",
            )


class TestExecutePlan:
    def test_dry_run_does_not_write(self, tmp_path: pathlib.Path):
        """dry_run should return GeneratedFile objects without writing."""
        output = tmp_path / "zros2_msgs"
        plan = build_plan(
            user_dirs=[],
            output_dir=output,
            distro="humble",
            root_package="zros2_msgs",
        )
        generated = execute_plan(plan, dry_run=True)
        assert generated
        assert not output.exists()
        assert all(
            hasattr(item, "path") and hasattr(item, "content") for item in generated
        )


class TestRootInitUpdate:
    """Tests for ``_update_root_init`` in ``pipeline/generate.py``."""

    def test_root_init_import_appended_when_missing(self, tmp_path: pathlib.Path):
        """When root __init__.py already exists but lacks registry import,
        the import line is appended (covers line 256-257).

        We test this indirectly via ``generate_all``: when the output directory
        already contains an ``__init__.py`` that is missing the registry import,
        # ``_update_root_init`` appends it.
        """
        from zros2.generator.codegen._message import GeneratedFile
        from zros2.generator.pipeline._generate import _update_root_init

        output_dir = tmp_path / "out"
        output_dir.mkdir(parents=True)
        root_init = output_dir / "__init__.py"
        root_init.write_text("# existing init\n")

        files: list[GeneratedFile] = [
            GeneratedFile(root_init, "# existing init\n"),
        ]
        _update_root_init(files, output_dir, distro="humble")
        # The import line should have been appended
        assert "from ._registry import" in files[0].content

    def test_root_init_import_already_present(self, tmp_path: pathlib.Path):
        """When root __init__.py already has the registry import, it is not
        duplicated (the function returns early after the for-loop        # Covers the early-return path in ``_update_root_init``.
        """
        from zros2.generator.codegen._message import GeneratedFile
        from zros2.generator.pipeline._generate import _update_root_init

        output_dir = tmp_path / "out"
        output_dir.mkdir(parents=True)
        root_init = output_dir / "__init__.py"
        existing_content = (
            "# existing init\n"
            "from ._registry import has_type, get_type, get_service, get_action, iter_types  # noqa: F401\n"
        )
        root_init.write_text(existing_content)

        files: list[GeneratedFile] = [
            GeneratedFile(root_init, existing_content),
        ]
        _original_content = files[0].content
        _update_root_init(files, output_dir)
        # Content should remain unchanged (import already present)
        assert files[0].content == existing_content

    def test_root_init_created_when_missing_from_files(self, tmp_path: pathlib.Path):
        """When root __init__.py is not in the files list, it is create        # Covers the file-creation path (lines 260-271)."""
        from zros2.generator.codegen._message import GeneratedFile
        from zros2.generator.pipeline._generate import _update_root_init

        output_dir = tmp_path / "out"
        output_dir.mkdir(parents=True)

        files: list[GeneratedFile] = []
        _update_root_init(files, output_dir, distro="humble")
        # A new GeneratedFile for __init__.py should have been appended
        assert len(files) == 1
        assert files[0].path == output_dir / "__init__.py"
        assert "._registry import" in files[0].content
