"""Directory scanning, type collection, and dependency validation.

Given one or more ROS 2 package directories, discovers ``.msg`` / ``.srv`` /
``.action`` files, parses them into ``MsgDefinition`` IR nodes, and verifies
that all cross-referenced types exist in the merged type dictionary.
"""

import pathlib
import re
from collections.abc import Iterator

from ..assets import BUILTIN_MSG_DIR
from .models import MsgDefinition
from .parser import (
    parse_action_file,
    parse_msg_file,
    parse_srv_file,
)
from .types import ROS2_PRIMITIVE_TYPES

# ═══════════════════════════════════════════════════════════════════════════
# Builtin message discovery
# ═══════════════════════════════════════════════════════════════════════════

DISTRO_MAP: dict[str, str] = {
    "humble": "humble",
    "iron": "iron",
    "jazzy": "jazzy",
    "kilted": "kilted",
    "lyrical": "lyrical",
}

VALID_DISTROS: tuple[str, ...] = tuple(DISTRO_MAP)


def builtin_msg_dirs(distro: str) -> list[pathlib.Path]:
    """Return the package directories for a given ROS 2 distro's builtin types."""
    if distro not in DISTRO_MAP:
        return []
    distro_dir = BUILTIN_MSG_DIR / DISTRO_MAP[distro]
    if not distro_dir.is_dir():
        return []
    return sorted(distro_dir.iterdir())


# ═══════════════════════════════════════════════════════════════════════════
# File iterators
# ═══════════════════════════════════════════════════════════════════════════


def iter_msg_files(msg_dir: pathlib.Path) -> Iterator[tuple[str, pathlib.Path]]:
    """Yield ``(package_name, file_path)`` for every ``.msg`` file found."""
    if not msg_dir.is_dir():
        return
    package = msg_dir.parent.name if msg_dir.parent.name else msg_dir.name
    for path in sorted(msg_dir.glob("*.msg")):
        yield package, path


def iter_srv_files(srv_dir: pathlib.Path) -> Iterator[tuple[str, pathlib.Path]]:
    """Yield ``(package_name, file_path)`` for every ``.srv`` file found."""
    if not srv_dir.is_dir():
        return
    package = srv_dir.parent.name if srv_dir.parent.name else srv_dir.name
    for path in sorted(srv_dir.glob("*.srv")):
        yield package, path


def iter_action_files(action_dir: pathlib.Path) -> Iterator[tuple[str, pathlib.Path]]:
    """Yield ``(package_name, file_path)`` for every ``.action`` file found."""
    if not action_dir.is_dir():
        return
    package = action_dir.parent.name if action_dir.parent.name else action_dir.name
    for path in sorted(action_dir.glob("*.action")):
        yield package, path


def find_msg_dirs(base_paths: list[pathlib.Path]) -> list[pathlib.Path]:
    """Collect all existing ``msg/`` subdirectories from the given base paths."""
    dirs: list[pathlib.Path] = []
    for base in base_paths:
        if not base.is_dir():
            continue
        msg_dir = base / "msg"
        if msg_dir.is_dir():
            dirs.append(base)
        else:
            for pkg_dir in sorted(base.iterdir()):
                if pkg_dir.is_dir() and (pkg_dir / "msg").is_dir():
                    dirs.append(pkg_dir)
    return dirs


# ═══════════════════════════════════════════════════════════════════════════
# Dependency validation
# ═══════════════════════════════════════════════════════════════════════════


def _strip_wrappers(raw: str) -> str:
    """Strip array/sequence/bounded_str wrappers to get the inner type name."""
    m = re.match(r"^(\w[\w/]*)\[\d*\]$", raw)
    if m:
        return m.group(1)
    m = re.match(r"^(\w[\w/]*)\[\]$", raw)
    if m:
        return m.group(1)
    m = re.match(r"^sequence<(\w[\w/]*)", raw)
    if m:
        return m.group(1)
    m = re.match(r"^string<=?\d+$", raw)
    if m:
        return "string"
    return raw


def _resolve_full_name(raw_type: str, current_package: str) -> str:
    """Resolve a raw type string to a fully qualified ``package/msg/TypeName``."""
    base = _strip_wrappers(raw_type.strip())
    if not base:
        return ""
    if base in ROS2_PRIMITIVE_TYPES or base in (
        "bool",
        "str",
        "int",
        "float",
        "time",
        "duration",
    ):
        return ""
    if "/msg/" in base or "/srv/" in base or "/action/" in base:
        return base
    if "/" not in base:
        return f"{current_package}/msg/{base}"
    if base.count("/") == 1:
        pkg, name = base.split("/", 1)
        return f"{pkg}/msg/{name}"
    return base


def validate_dependencies(types: dict[str, MsgDefinition]) -> None:
    """Check that every non-primitive type reference in *types* exists.

    Raises:
        ValueError: With a message listing every missing dependency.
    """
    missing: list[tuple[str, str, str]] = []
    for name, defn in types.items():
        for field in defn.fields:
            full = _resolve_full_name(field.type_str, defn.package)
            if not full:
                continue
            if full not in types:
                missing.append((name, field.name, full))
    if missing:
        lines = [
            f"  {owner}: field '{field}' -> {typ}" for owner, field, typ in missing
        ]
        msg = (
            "Missing type dependencies -- make sure all required packages\n"
            "are included in --msg-dirs or are part of the selected ROS 2 "
            "distro:\n\n" + "\n".join(lines)
        )
        raise ValueError(msg)


# ═══════════════════════════════════════════════════════════════════════════
# Type collection
# ═══════════════════════════════════════════════════════════════════════════


def collect_all_types(
    msg_dirs: list[pathlib.Path],
) -> dict[str, MsgDefinition]:
    """Scan directories for all .msg, .srv, .action files and parse them."""
    types: dict[str, MsgDefinition] = {}

    for pkg_dir in msg_dirs:
        package = pkg_dir.name

        # -- Messages --
        msg_dir = pkg_dir / "msg"
        for _, file_path in iter_msg_files(msg_dir):
            defn = parse_msg_file(file_path, package)
            types[defn.full_name] = defn

        # -- Services --
        srv_dir = pkg_dir / "srv"
        for _, file_path in iter_srv_files(srv_dir):
            request, response = parse_srv_file(file_path, package)
            types[request.full_name] = request
            types[response.full_name] = response

        # -- Actions --
        action_dir = pkg_dir / "action"
        for _, file_path in iter_action_files(action_dir):
            for defn in parse_action_file(file_path, package):
                types[defn.full_name] = defn

    return types


__all__ = [
    "DISTRO_MAP",
    "VALID_DISTROS",
    "builtin_msg_dirs",
    "collect_all_types",
    "find_msg_dirs",
    "iter_action_files",
    "iter_msg_files",
    "iter_srv_files",
    "validate_dependencies",
]
