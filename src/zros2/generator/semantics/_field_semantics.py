"""Semantic facts about one message field."""

from dataclasses import dataclass

from zros2.generator.parsing._models import MsgDefinition, MsgField
from zros2.generator.parsing._types import TypeInfo, parse_type

from ._native_types import is_container, python_type
from ._resolve_types import ResolvedType, inner_type_str
from ._type_context import TypeContext, build_type_context


@dataclass(frozen=True)
class FieldSemantics:
    """Resolved type information shared by runtime and stub renderers."""

    field: MsgField
    info: TypeInfo
    resolved: ResolvedType
    native_type: str
    is_container: bool
    is_nested: bool


def build_field_semantics(
    field: MsgField,
    defn: MsgDefinition,
    root_package: str,
    context: TypeContext | None = None,
) -> FieldSemantics:
    """Resolve one field against its parent message definition."""
    ctx = context or build_type_context(defn, root_package)
    info = parse_type(field.type_str)
    resolved = ctx.resolve(field.type_str)
    container = is_container(info)
    if container:
        inner_info = parse_type(inner_type_str(info))
        inner_resolved = ctx.resolve(inner_type_str(info))
        inner_native = python_type(inner_info, inner_resolved)
        native = f"Sequence[{inner_native}]"
    else:
        native = python_type(info, resolved)
    return FieldSemantics(
        field=field,
        info=info,
        resolved=resolved,
        native_type=native,
        is_container=container,
        is_nested=bool(resolved.external_import),
    )


__all__ = ["FieldSemantics", "build_field_semantics"]
