"""Field planning: AST annotations, defaults, and __init__ statements."""

import ast
from dataclasses import dataclass

from zros2.generator.codegen._literal_ast import literal_ast
from zros2.generator.parsing._models import MsgDefinition, MsgField
from zros2.generator.parsing._types import TypeInfo
from zros2.generator.semantics._field_semantics import FieldSemantics, build_field_semantics
from zros2.generator.semantics._literal_values import default_scalar, parse_literal
from zros2.generator.semantics._native_types import SEQUENCE_KINDS
from zros2.generator.semantics._resolve_types import ResolvedType, inner_type_str, resolve_type
from zros2.generator.semantics._type_context import TypeContext

from ._defaults import _container_default

# ═══════════════════════════════════════════════════════════════════════════
# AST helpers
# ═══════════════════════════════════════════════════════════════════════════


def _assign(name: str, value: ast.expr) -> ast.Assign:
    return ast.Assign(targets=[ast.Name(id=name)], value=value)


def _type_alias(name: str, expr: str) -> ast.AnnAssign:
    return ast.AnnAssign(
        target=ast.Name(id=name),
        annotation=ast.Name(id="TypeAlias"),
        value=ast.parse(expr, mode="eval").body,
        simple=1,
    )


def _is_none(name: str) -> ast.expr:
    return ast.Compare(
        left=ast.Name(id=name),
        ops=[ast.Is()],
        comparators=[ast.Constant(value=None)],
    )


def _assign_field(field_name: str, value: ast.expr) -> ast.Assign:
    return ast.Assign(
        targets=[ast.Attribute(value=ast.Name(id="self"), attr=field_name)],
        value=value,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Hardcoded to_dict / from_dict generation
# ═══════════════════════════════════════════════════════════════════════════


def _normalize_container(
    info: TypeInfo,
    name: str,
    defn: MsgDefinition,
    root_package: str,
    constants: dict[str, int],
) -> ast.expr:
    """Wrap a container argument so it matches the deserialized container type."""
    if info.kind in SEQUENCE_KINDS:
        return ast.Call(func=ast.Name(id="list"), args=[ast.Name(id=name)], keywords=[])
    inner_resolved = resolve_type(
        inner_type_str(info),
        defn.package,
        root_package,
        constants=constants,
    )
    if inner_resolved.annotation_expr == "uint8":
        return ast.Call(func=ast.Name(id="bytes"), args=[ast.Name(id=name)], keywords=[])
    return ast.Call(func=ast.Name(id="tuple"), args=[ast.Name(id=name)], keywords=[])


@dataclass
class _FieldPlan:
    field: MsgField
    info: TypeInfo
    resolved: ResolvedType
    ann_name: str
    init_name: str
    default_name: str
    class_default: ast.expr
    init_default: ast.expr
    init_type: str
    init_stmt: ast.stmt
    module_stmts: list[ast.stmt]
    needs_field: bool
    needs_sequence: bool


def _plan_field(
    field: MsgField,
    index: int,
    defn: MsgDefinition,
    root_package: str,
    class_token: str,
    type_context: TypeContext,
) -> _FieldPlan:
    """Resolve one field and build all of its generated declarations."""
    resolved_field: FieldSemantics = build_field_semantics(
        field, defn, root_package, context=type_context
    )
    info = resolved_field.info
    resolved = resolved_field.resolved
    field_context = f"{defn.full_name}.{field.name}"
    for bound in (info.array_size, info.array_max, info.string_max):
        if isinstance(bound, str):
            type_context.bound(bound, field_context)
    constants = dict(type_context.constants)
    is_container = resolved_field.is_container
    is_nested = resolved_field.is_nested

    ann_name = f"_ZROS2_{class_token}_T{index}"
    init_name = f"_ZROS2_{class_token}_IT{index}"
    default_name = f"_ZROS2_{class_token}_D{index}"
    module_stmts: list[ast.stmt] = [_type_alias(ann_name, resolved.annotation_expr)]

    needs_field = False
    needs_sequence = False

    if field.default is not None:
        if is_container or is_nested:
            raise ValueError(
                f"{field_context}: default values are only supported for scalar fields"
            )
        value = parse_literal(field.default, info, field_context)
        default_node = literal_ast(value)
        init_type = resolved_field.native_type
        init_default: ast.expr = ast.Name(id=default_name)
        init_stmt = _assign_field(field.name, ast.Name(id=field.name))
    elif is_container:
        default_node = _container_default(
            info,
            constants,
            context=field_context,
            defn=defn,
            root_package=root_package,
        )
        if info.kind in SEQUENCE_KINDS:
            default_node = ast.Call(
                func=ast.Name(id="field"),
                args=[],
                keywords=[ast.keyword(arg="default_factory", value=ast.Name(id="list"))],
            )
            needs_field = True
        init_type = f"{resolved_field.native_type} | None"
        needs_sequence = True
        init_default = ast.Constant(value=None)
        init_stmt = _assign_field(
            field.name,
            ast.IfExp(
                test=_is_none(field.name),
                body=_container_default(
                    info,
                    constants,
                    context=field_context,
                    defn=defn,
                    root_package=root_package,
                ),
                orelse=_normalize_container(
                    info, field.name, defn, root_package, constants
                ),
            ),
        )
    elif is_nested:
        default_node = ast.Call(
            func=ast.Name(id="field"),
            args=[],
            keywords=[
                ast.keyword(
                    arg="default_factory",
                    value=ast.Name(id=resolved.annotation_expr),
                )
            ],
        )
        needs_field = True
        init_type = f"{resolved_field.native_type} | None"
        init_default = ast.Constant(value=None)
        init_stmt = _assign_field(
            field.name,
            ast.IfExp(
                test=_is_none(field.name),
                body=ast.Call(
                    func=ast.Name(id=resolved.annotation_expr), args=[], keywords=[]
                ),
                orelse=ast.Name(id=field.name),
            ),
        )
    else:
        default_node = literal_ast(default_scalar(info))
        init_type = resolved_field.native_type
        init_default = ast.Name(id=default_name)
        init_stmt = _assign_field(field.name, ast.Name(id=field.name))

    module_stmts.append(_assign(default_name, default_node))
    return _FieldPlan(
        field=field,
        info=info,
        resolved=resolved,
        ann_name=ann_name,
        init_name=init_name,
        default_name=default_name,
        class_default=ast.Name(id=default_name),
        init_default=init_default,
        init_type=init_type,
        init_stmt=init_stmt,
        module_stmts=module_stmts,
        needs_field=needs_field,
        needs_sequence=needs_sequence,
    )

__all__ = ["_FieldPlan", "_assign", "_plan_field", "_type_alias"]
