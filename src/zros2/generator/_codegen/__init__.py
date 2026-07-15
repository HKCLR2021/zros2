"""
Code generation back-end for ``zros2-gen``.

This package is the internal engine that turns parsed ROS 2 interface definitions
into Python source files.  Each sub-module is responsible for one piece of the
output:

* ``_msg``       — Generates the ``.py`` module for a single message, service, or
                   action definition (e.e. ``Foo.msg`` → ``_foo.py``).  This is
                   the core translation layer that maps ROS 2 field types onto
                   Python type annotations and the zros2 runtime API.

* ``_pyi``       — Generates the corresponding ``.pyi`` stub file, providing
                   type-checkers with the same public interface without the
                   runtime machinery.

* ``_init``      — Generates ``__init__.py`` files at two levels:
                    1. Per-subdirectory indexes that re-export every type and
                       register message types for run-time name lookup.
                    2. Package-level ``__init__.py`` that imports ``msg``,
                       ``srv``, ``action`` sub-packages so they form a
                       conventional ROS 2 Python package tree.

* ``_srv_action`` — Generates combined service/action wrapper modules.  Unlike
                    plain messages, services and actions produce multiple
                    interrelated types (Request, Response, etc.) that need
                    shared metadata and a unified API surface.

* ``_registry``   — Builds the abstract-syntax tree for the run-time type
                    registry (``_registry.py``), a lookup table that maps
                    qualified ROS 2 type names (e.g. ``std_msgs/msg/String``)
                    to their Python classes so tools like ``zros2`` can resolve
                    types by string at run time.

* ``_orchestrator`` — Ties everything together: discovers ROS 2 interfaces,
                     dispatches each definition to the correct sub-module,
                     collects the generated outputs, and writes them to disk.
"""

from ._msg import (
    GeneratedFile,
    _registry_import,
    _needs_optional_annotation,
    generate_message_module,
)

from ._pyi import (
    generate_stub_module,
)

from ._init import (
    generate_init_module,
    generate_package_init,
)

from ._srv_action import (
    _SRV_SUFFIXES,
    _ACTION_SUFFIXES,
    _generate_service_wrappers,
    _generate_action_wrappers,
)

from ._registry import (
    _REGISTRY_AST,
)

from ._orchestrator import (
    BUILTIN_MSG_DIR,
    VALID_DISTROS,
    builtin_msg_dirs,
    validate_dependencies,
    collect_all_types,
    generate_all,
    write_generated_files,
)

__all__ = [
    "GeneratedFile",
    "_registry_import",
    "_needs_optional_annotation",
    "generate_message_module",
    "generate_stub_module",
    "generate_init_module",
    "generate_package_init",
    "_SRV_SUFFIXES",
    "_ACTION_SUFFIXES",
    "_generate_service_wrappers",
    "_generate_action_wrappers",
    "_REGISTRY_AST",
    "BUILTIN_MSG_DIR",
    "VALID_DISTROS",
    "builtin_msg_dirs",
    "validate_dependencies",
    "collect_all_types",
    "generate_all",
    "write_generated_files",
]
