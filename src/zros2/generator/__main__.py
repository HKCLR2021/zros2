"""CLI entry point for zros2.generator.

Scans directories for ``.msg``, ``.srv``, and ``.action`` files, merges them
with the selected ROS 2 distro's builtin types (all bundled builtins are
generated), and produces Python dataclass modules using ``pycdr2.IdlMeta``.

The output directory is a valid Python package:

    zros2-gen --msg-dirs ./my_msgs --ros-version humble \\
              --root-package zros2_msgs --output ./zros2_msgs

    # import anywhere via:
    from zros2_msgs.std_msgs.msg import String

Add the parent of ``--output`` to ``PYTHONPATH``.
"""

import argparse
import pathlib
import sys

from . import (
    collect_all_types,
    generate_all,
    write_generated_files,
    validate_dependencies,
    builtin_msg_dirs,
    VALID_DISTROS,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="zros2-gen",
        description="Generate Python dataclass code from ROS2 .msg / .srv / .action files.",
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
        "--output", "-o",
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
            "Pass an explicit empty string (``--root-package \"\"``) "
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


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    user_dirs: list[pathlib.Path] = []
    for p in args.msg_dirs:
        resolved = p.resolve()
        if not resolved.is_dir():
            parser.error(f"Input directory does not exist: {resolved}")
        user_dirs.append(resolved)

    output_dir = args.output.resolve()

    # --- collect builtin types ---
    print(f"Loading ROS 2 {args.ros_version} builtin types ...")
    builtin_pkg_dirs = builtin_msg_dirs(args.ros_version)
    builtin_types = collect_all_types(builtin_pkg_dirs) if builtin_pkg_dirs else {}
    print(f"  {len(builtin_types)} builtin type(s) loaded")

    # --- collect user types ---
    user_types: dict = {}
    if user_dirs:
        print(f"Scanning {len(user_dirs)} user package director{'y' if len(user_dirs) == 1 else 'ies'} ...")
        user_types = collect_all_types(user_dirs)
        print(f"  {len(user_types)} user type(s) found")
        for name in sorted(user_types):
            print(f"    - {name}")

    # --- merge ---
    merged = {}
    merged.update(builtin_types)
    merged.update(user_types)

    # --- validate ---
    print("Validating dependencies ...")
    try:
        validate_dependencies(merged)
        print("  All dependencies resolved.")
    except ValueError as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        sys.exit(1)

    # --- default root_package to output directory name ---
    if args.root_package is None:
        args.root_package = output_dir.name

    # --- generate ---
    generated = generate_all(merged, output_dir, root_package=args.root_package,
                              distro=args.ros_version)

    if args.dry_run:
        print(f"\nWould generate {len(generated)} file(s):")
        for gf in generated:
            print(f"  {gf.path}")
        return

    written = write_generated_files(generated)
    print(f"\nGenerated {len(written)} file(s) in {output_dir}:")
    for path in written[:25]:
        print(f"  {path.relative_to(output_dir.parent)}")
    if len(written) > 25:
        print(f"  ... and {len(written) - 25} more")

    print("\nDone.")


if __name__ == "__main__":
    main()
