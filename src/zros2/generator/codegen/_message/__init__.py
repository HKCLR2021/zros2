"""Code generation for ROS 2 message modules.

The public entry point is :func:`generate_message_module`.  The implementation
is split into three layers:

* :mod:`._plan` \u2014 field resolution and AST defaults;
* :mod:`._methods` \u2014 ``to_dict`` / ``from_dict`` / ``from_attributes``;
* :mod:`._assemble` \u2014 module imports, class body, and final source.
"""

from zros2.generator.codegen._file import GeneratedFile as GeneratedFile
from zros2.generator.codegen._registry import registry_import

from ._assemble import generate_message_module

__all__ = ["GeneratedFile", "generate_message_module", "registry_import"]
