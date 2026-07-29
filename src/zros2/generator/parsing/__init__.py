"""ROS 2 interface and type-expression parsing.

Three sub-modules provide a clean layered API:

* ``models`` — IR dataclasses (``MsgField``, ``MsgDefinition``)
* ``types`` — Lark grammar + ``TypeInfo`` / ``parse_type()``
* ``parser`` — text → IR (``parse_msg_text`` / ``parse_msg_file`` …)
* ``discovery`` — directory scanning, type collection, dependency checks
"""

from .discovery import (
    VALID_DISTROS,
    builtin_msg_dirs,
    collect_all_types,
    find_msg_dirs,
    iter_action_files,
    iter_msg_files,
    iter_srv_files,
    validate_dependencies,
)
from .models import MsgDefinition, MsgField
from .parser import (
    parse_action_file,
    parse_msg_file,
    parse_msg_text,
    parse_srv_file,
)
from .types import ROS2_PRIMITIVE_TYPES, TypeInfo, parse_type

__all__ = [
    "ROS2_PRIMITIVE_TYPES",
    "VALID_DISTROS",
    "MsgDefinition",
    "MsgField",
    "TypeInfo",
    "builtin_msg_dirs",
    "collect_all_types",
    "find_msg_dirs",
    "iter_action_files",
    "iter_msg_files",
    "iter_srv_files",
    "parse_action_file",
    "parse_msg_file",
    "parse_msg_text",
    "parse_srv_file",
    "parse_type",
    "validate_dependencies",
]
