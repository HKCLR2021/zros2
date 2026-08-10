"""CLI for ``zros2-gen`` / ``python -m zros2.generator``."""

import argparse
import pathlib
import sys

from .parsing._discovery import VALID_DISTROS
from .pipeline._plan import build_plan, execute_plan


def build_parser() -> argparse.ArgumentParser:
    """Return the configured argument parser for the generator CLI."""
    parser = argparse.ArgumentParser(
        prog="zros2-gen",
        description=(
            "Generate Python dataclass code from ROS2 .msg / .srv / .action files."
        ),
    )
    parser.add_argument(
        "--msg-dirs",
        nargs="+",
        required=True,
        type=pathlib.Path,
        help=(
            "One or more ROS2 package directories containing msg/, srv/, and/or "
            "action/ subfolders."
        ),
    )
    parser.add_argument(
        "--output",
        "-o",
        required=True,
        type=pathlib.Path,
        help="Output directory for generated Python source files.",
    )
    parser.add_argument(
        "--root-package",
        default=None,
        type=str,
        help=(
            "Top-level package prefix for import paths. "
            "Generated imports use ``{root_package}.pkg.msg.Type``. "
            "When omitted, defaults to the output directory name. "
            'Pass an explicit empty string (``--root-package ""``) '
            "to suppress the prefix entirely."
        ),
    )
    parser.add_argument(
        "--ros-version",
        required=True,
        choices=VALID_DISTROS,
        help="ROS 2 distribution whose builtin types to bundle (required).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print generated file list without writing anything.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    """Parse CLI arguments and run the generation pipeline."""
    parser = build_parser()
    args = parser.parse_args(argv)

    user_dirs: list[pathlib.Path] = []
    for path in args.msg_dirs:
        resolved = path.resolve()
        if not resolved.is_dir():
            parser.error(f"Input directory does not exist: {resolved}")
        user_dirs.append(resolved)

    output_dir = args.output.resolve()

    print(f"Loading ROS 2 {args.ros_version} builtin types ...")
    print("Validating dependencies ...")
    try:
        plan = build_plan(
            user_dirs=user_dirs,
            output_dir=output_dir,
            distro=args.ros_version,
            root_package=args.root_package,
        )
    except ValueError as error:
        print(f"\nERROR: {error}", file=sys.stderr)
        sys.exit(1)

    print("  All dependencies resolved.")
    print(f"  {plan.builtin_count} builtin type(s) loaded")
    if user_dirs:
        label = "y" if len(user_dirs) == 1 else "ies"
        print(f"Scanning {len(user_dirs)} user package director{label} ...")
        print(f"  {len(plan.user_type_names)} user type(s) found")
        for name in plan.user_type_names:
            print(f"    - {name}")

    if args.dry_run:
        dry_files = execute_plan(plan, dry_run=True)
        print(f"\nWould generate {len(dry_files)} file(s):")
        for generated in dry_files:
            print(f"  {generated.path}")
        return

    written = execute_plan(plan, dry_run=False)
    print(f"\nGenerated {len(written)} file(s) in {output_dir}:")
    for path in written[:25]:
        print(f"  {path.relative_to(output_dir.parent)}")
    if len(written) > 25:
        print(f"  ... and {len(written) - 25} more")
    print("\nDone.")


__all__ = ["build_parser", "main"]
