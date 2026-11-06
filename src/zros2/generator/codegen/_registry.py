"""Registry AST builder — assembles the generated runtime registry."""

import ast

from ._registry_actions import _reg_action_section
from ._registry_common import _reg_header, _reg_helper
from ._registry_messages import _reg_message_section
from ._registry_services import _reg_service_section


def registry_import(root_package: str) -> str:
    """Return the import module for the generated runtime registry."""
    if root_package:
        return root_package + "._registry"
    return "_registry"


# Section order is significant: the helper must come last because
# ``_raise_not_found`` references ``_TYPES``.
REGISTRY_AST = ast.Module(
    body=(
        _reg_header()
        + _reg_message_section()
        + _reg_service_section()
        + _reg_action_section()
        + _reg_helper()
    ),
    type_ignores=[],
)
ast.fix_missing_locations(REGISTRY_AST)

__all__ = ["REGISTRY_AST", "registry_import"]
