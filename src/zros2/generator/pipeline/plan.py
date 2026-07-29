"""Collect, merge, and validate a generation plan."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, overload

from ..codegen.message import GeneratedFile
from ..parsing.discovery import (
    builtin_msg_dirs,
    collect_all_types,
    validate_dependencies,
)
from ..parsing.models import MsgDefinition
from .generate import generate_all
from .writer import write_generated_files


@dataclass(frozen=True)
class GenerationPlan:
    """Fully resolved inputs for a generator run."""

    types: dict[str, MsgDefinition]
    output_dir: Path
    root_package: str
    distro: str
    builtin_count: int
    user_type_names: tuple[str, ...]


def build_plan(
    user_dirs: list[Path],
    output_dir: Path,
    distro: str,
    root_package: str | None = None,
) -> GenerationPlan:
    """Collect builtin/user types, merge them, and validate dependencies.

    Args:
        user_dirs: ROS 2 package directories containing msg/srv/action.
        output_dir: Destination directory for generated sources.
        distro: ROS 2 distribution name for builtin assets.
        root_package: Optional import prefix. Defaults to ``output_dir.name``.

    Returns:
        A validated :class:`GenerationPlan`.

    Raises:
        ValueError: If dependencies cannot be resolved.
    """
    builtin_pkg_dirs = builtin_msg_dirs(distro)
    builtin_types = collect_all_types(builtin_pkg_dirs) if builtin_pkg_dirs else {}
    user_types = collect_all_types(user_dirs) if user_dirs else {}

    merged = dict(builtin_types)
    merged.update(user_types)
    validate_dependencies(merged)

    resolved_root = output_dir.name if root_package is None else root_package
    return GenerationPlan(
        types=merged,
        output_dir=output_dir,
        root_package=resolved_root,
        distro=distro,
        builtin_count=len(builtin_types),
        user_type_names=tuple(sorted(user_types)),
    )


@overload
def execute_plan(
    plan: GenerationPlan, *, dry_run: Literal[True]
) -> list[GeneratedFile]: ...
@overload
def execute_plan(
    plan: GenerationPlan, *, dry_run: Literal[False] = False
) -> list[Path]: ...
def execute_plan(
    plan: GenerationPlan, *, dry_run: bool = False
) -> list[GeneratedFile] | list[Path]:
    """Generate sources for *plan*, optionally writing them to disk.

    Returns:
        The list of :class:`~zros2.generator.codegen.message.GeneratedFile`
        objects when ``dry_run`` is true; otherwise the list of written paths.
    """
    generated = generate_all(
        plan.types,
        plan.output_dir,
        root_package=plan.root_package,
        distro=plan.distro,
    )
    if dry_run:
        return generated
    return write_generated_files(generated)


__all__ = ["GenerationPlan", "build_plan", "execute_plan"]
