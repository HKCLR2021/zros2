"""Unit tests for the generator planning pipeline."""

import pathlib

import pytest

from zros2.generator.pipeline.plan import GenerationPlan, build_plan, execute_plan


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
        assert all(hasattr(item, "path") and hasattr(item, "content") for item in generated)
