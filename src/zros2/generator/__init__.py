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

from ._parser import (
    MsgField,
    MsgDefinition,
    parse_msg_text,
    parse_msg_file,
    parse_srv_file,
    parse_action_file,
    iter_msg_files,
    iter_srv_files,
    iter_action_files,
    find_msg_dirs,
)

from ._type_map import (
    ResolvedType,
    resolve_type,
    is_primitive,
    get_default_value,
)

from ._codegen import (
    generate_message_module,
    generate_stub_module,
    generate_init_module,
    generate_package_init,
    GeneratedFile,
    collect_all_types,
    generate_all,
    write_generated_files,
    validate_dependencies,
    builtin_msg_dirs,
    BUILTIN_MSG_DIR,
    VALID_DISTROS,
)

__all__ = [
    # Parser
    "MsgField",
    "MsgDefinition",
    "parse_msg_text",
    "parse_msg_file",
    "parse_srv_file",
    "parse_action_file",
    "iter_msg_files",
    "iter_srv_files",
    "iter_action_files",
    "find_msg_dirs",
    # Type map
    "ResolvedType",
    "resolve_type",
    "is_primitive",
    "get_default_value",
    # Generator
    "generate_message_module",
    "generate_stub_module",
    "generate_init_module",
    "generate_package_init",
    "collect_all_types",
    "generate_all",
    "write_generated_files",
    "GeneratedFile",
    "validate_dependencies",
    "builtin_msg_dirs",
    "BUILTIN_MSG_DIR",
    "VALID_DISTROS",
]
