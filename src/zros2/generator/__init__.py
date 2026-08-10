"""zros2.generator — ROS 2 message code generator.

Generates Python dataclass modules from ``.msg``, ``.srv``, and ``.action``
files using ``pycdr2.IdlMeta`` (preserving full type annotations).

Built-in ROS 2 types are bundled per distro (humble, iron, jazzy, kilted,
lyrical).  All bundled types are generated; user types override builtins
of the same name.

Usage:
    zros2-gen --msg-dirs ./my_msgs --ros-version humble --output ./gen
    python -m zros2.generator --msg-dirs ./pkg_a ./pkg_b --ros-version jazzy --output ./gen
"""

from .parsing import (
    VALID_DISTROS,
    MsgDefinition,
    MsgField,
    parse_action_file,
    parse_msg_file,
    parse_msg_text,
    parse_srv_file,
)
from .pipeline import generate_all
from .semantics import ResolvedType, resolve_type

__all__ = [
    "VALID_DISTROS",
    "MsgDefinition",
    "MsgField",
    "ResolvedType",
    "generate_all",
    "parse_action_file",
    "parse_msg_file",
    "parse_msg_text",
    "parse_srv_file",
    "resolve_type",
]
