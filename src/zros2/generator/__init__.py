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

from .assets import BUILTIN_MSG_DIR
from .codegen import (
    GeneratedFile,
    generate_init_module,
    generate_message_module,
    generate_package_init,
    generate_stub_module,
)
from .parsing import (
    VALID_DISTROS,
    MsgDefinition,
    MsgField,
    builtin_msg_dirs,
    collect_all_types,
    find_msg_dirs,
    iter_action_files,
    iter_msg_files,
    iter_srv_files,
    parse_action_file,
    parse_msg_file,
    parse_msg_text,
    parse_srv_file,
    validate_dependencies,
)
from .pipeline import (
    generate_all,
    write_generated_files,
)
from .semantics import (
    ResolvedType,
    get_default_value,
    is_primitive,
    resolve_type,
)

__all__ = [
    "BUILTIN_MSG_DIR",
    "VALID_DISTROS",
    "GeneratedFile",
    "MsgDefinition",
    "MsgField",
    "ResolvedType",
    "builtin_msg_dirs",
    "collect_all_types",
    "find_msg_dirs",
    "generate_all",
    "generate_init_module",
    "generate_message_module",
    "generate_package_init",
    "generate_stub_module",
    "get_default_value",
    "is_primitive",
    "iter_action_files",
    "iter_msg_files",
    "iter_srv_files",
    "parse_action_file",
    "parse_msg_file",
    "parse_msg_text",
    "parse_srv_file",
    "resolve_type",
    "validate_dependencies",
    "write_generated_files",
]
