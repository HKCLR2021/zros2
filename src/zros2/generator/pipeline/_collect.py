"""Collect parsed interface definitions from ROS 2 package directories."""

import pathlib

from zros2.generator.parsing._discovery import (
    iter_action_files,
    iter_msg_files,
    iter_srv_files,
)
from zros2.generator.parsing._models import MsgDefinition
from zros2.generator.parsing._parser import (
    parse_action_file,
    parse_msg_file,
    parse_srv_file,
)
from zros2.generator.semantics._action import expand_action


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
        # Parser yields the three user sections; expansion adds the five
        # transport types so dependency validation sees the full set.
        action_dir = pkg_dir / "action"
        for _, file_path in iter_action_files(action_dir):
            for defn in expand_action(parse_action_file(file_path, package)):
                types[defn.full_name] = defn

    return types


__all__ = ["collect_all_types"]
