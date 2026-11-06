"""to_dict / from_dict / from_attributes generation for message classes."""

import ast

from zros2.generator.parsing._models import MsgDefinition, MsgField
from zros2.generator.parsing._types import parse_type
from zros2.generator.semantics._native_types import CONTAINER_KINDS
from zros2.generator.semantics._resolve_types import inner_type_str
from zros2.generator.semantics._type_context import TypeContext


def _gen_to_dict_value(
    field: MsgField,
    defn: MsgDefinition,
    root_package: str,
    type_context: TypeContext,
) -> ast.expr:
    """Generate the ``to_dict`` value expression for one field."""
    info = parse_type(field.type_str)
    resolved = type_context.resolve(field.type_str)
    self_attr = ast.Attribute(value=ast.Name(id="self"), attr=field.name)

    if info.kind in CONTAINER_KINDS:
        inner_str = inner_type_str(info)
        inner_resolved = type_context.resolve(inner_str)
        if inner_resolved.external_import:
            return ast.ListComp(
                elt=ast.Call(
                    func=ast.Attribute(value=ast.Name(id="e"), attr="to_dict"),
                    args=[],
                    keywords=[],
                ),
                generators=[
                    ast.comprehension(
                        target=ast.Name(id="e"),
                        iter=self_attr,
                        ifs=[],
                        is_async=0,
                    )
                ],
            )
        return ast.Call(
            func=ast.Name(id="list"),
            args=[self_attr],
            keywords=[],
        )

    if resolved.external_import:
        return ast.Call(
            func=ast.Attribute(value=self_attr, attr="to_dict"),
            args=[],
            keywords=[],
        )
    return self_attr


def _gen_to_dict_method(
    defn: MsgDefinition,
    root_package: str,
    type_context: TypeContext,
) -> ast.FunctionDef:
    """Generate a hardcoded ``def to_dict(self) -> dict[str, Any]:``."""
    keys: list[ast.expr | None] = [ast.Constant(value=f.name) for f in defn.fields]
    values = [
        _gen_to_dict_value(f, defn, root_package, type_context) for f in defn.fields
    ]
    return ast.FunctionDef(
        name="to_dict",
        args=ast.arguments(
            posonlyargs=[],
            args=[ast.arg(arg="self")],
            kwonlyargs=[],
            kw_defaults=[],
            defaults=[],
        ),
        body=[ast.Return(value=ast.Dict(keys=keys, values=values))],
        decorator_list=[],
        returns=ast.Subscript(
            value=ast.Name(id="dict"),
            slice=ast.Tuple(elts=[ast.Name(id="str"), ast.Name(id="Any")]),
        ),
    )


def _gen_from_dict_value(
    field: MsgField,
    defn: MsgDefinition,
    root_package: str,
    type_context: TypeContext,
) -> ast.expr:
    """Generate the ``from_dict`` value expression for one field."""
    info = parse_type(field.type_str)
    resolved = type_context.resolve(field.type_str)
    data_sub = ast.Subscript(value=ast.Name(id="data"), slice=ast.Constant(value=field.name))

    if info.kind in CONTAINER_KINDS:
        inner_str = inner_type_str(info)
        inner_resolved = type_context.resolve(inner_str)
        if inner_resolved.external_import:
            return ast.ListComp(
                elt=ast.Call(
                    func=ast.Attribute(
                        value=ast.Name(id=inner_resolved.annotation_expr),
                        attr="from_dict",
                    ),
                    args=[ast.Name(id="item")],
                    keywords=[],
                ),
                generators=[
                    ast.comprehension(
                        target=ast.Name(id="item"),
                        iter=data_sub,
                        ifs=[],
                        is_async=0,
                    )
                ],
            )
        return data_sub

    if resolved.external_import:
        return ast.Call(
            func=ast.Attribute(
                value=ast.Name(id=resolved.annotation_expr),
                attr="from_dict",
            ),
            args=[data_sub],
            keywords=[],
        )
    return data_sub


def _gen_from_dict_method(
    defn: MsgDefinition,
    root_package: str,
    type_context: TypeContext,
) -> ast.FunctionDef:
    """Generate a hardcoded ``def from_dict(cls, data) -> ClassName:``."""
    class_name = defn.type_name.split("/")[-1].replace("-", "_")
    keywords = [
        ast.keyword(arg=f.name, value=_gen_from_dict_value(f, defn, root_package, type_context))
        for f in defn.fields
    ]
    return ast.FunctionDef(
        name="from_dict",
        args=ast.arguments(
            posonlyargs=[],
            args=[
                ast.arg(arg="cls"),
                ast.arg(
                    arg="data",
                    annotation=ast.Subscript(
                        value=ast.Name(id="dict"),
                        slice=ast.Tuple(elts=[ast.Name(id="str"), ast.Name(id="Any")]),
                    ),
                ),
            ],
            kwonlyargs=[],
            kw_defaults=[],
            defaults=[],
        ),
        body=[
            ast.Return(
                value=ast.Call(
                    func=ast.Name(id=class_name), args=[], keywords=keywords
                )
            )
        ],
        decorator_list=[ast.Name(id="classmethod")],
        returns=ast.Constant(value=class_name),
    )


# ═══════════════════════════════════════════════════════════════════════════
# Module generation
# ═══════════════════════════════════════════════════════════════════════════

__all__ = ["_gen_from_dict_method", "_gen_to_dict_method"]
