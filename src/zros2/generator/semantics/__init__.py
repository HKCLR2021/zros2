"""Type resolution, action IDL expansion, and shared generator utilities."""

from ._action import expand_action
from ._resolve_types import ResolvedType, resolve_type

__all__ = [
    "ResolvedType",
    "expand_action",
    "resolve_type",
]
