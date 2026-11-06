"""Build AST default expressions for message fields."""

import ast

from zros2.generator.parsing._models import MsgDefinition
from zros2.generator.parsing._types import TypeInfo, parse_type
from zros2.generator.semantics._native_types import (
    FLOAT_TYPES,
    INT_TYPES,
    SEQUENCE_KINDS,
    STRING_TYPES,
)
from zros2.generator.semantics._resolve_types import inner_type_str, resolve_type
from zros2.generator.semantics._type_context import resolve_size


def _zero_node(info: TypeInfo) -> ast.expr | None:
    """Return a zero/empty literal for a scalar element type."""
    base = info.base_name
    if info.is_bounded_string or base in STRING_TYPES:
        return ast.Constant(value="")
    if base == "bool":
        return ast.Constant(value=False)
    if base in INT_TYPES:
        return ast.Constant(value=0)
    if base in FLOAT_TYPES:
        return ast.Constant(value=0.0)
    return None


def _container_default(
    info: TypeInfo,
    constants: dict[str, int],
    *,
    context: str,
    defn: MsgDefinition,
    root_package: str,
) -> ast.expr:
    """Build the default value expression for an array/sequence field."""
    if info.kind in SEQUENCE_KINDS:
        return ast.List(elts=[], ctx=ast.Load())

    if info.kind != "fixed":
        raise ValueError(f"{context}: expected a fixed-size array")
    size = resolve_size(info.array_size, constants, context)
    if size == 0:
        return ast.Tuple(elts=[], ctx=ast.Load())

    inner = parse_type(inner_type_str(info))
    inner_resolved = resolve_type(
        inner_type_str(info),
        defn.package,
        root_package,
        constants=constants,
    )
    if inner_resolved.annotation_expr == "uint8" and not inner.is_bounded_string:
        return ast.BinOp(
            left=ast.Constant(value=b"\x00"),
            op=ast.Mult(),
            right=ast.Constant(value=size),
        )
    if inner_resolved.external_import:
        return ast.Call(
            func=ast.Name(id="tuple"),
            args=[
                ast.GeneratorExp(
                    elt=ast.Call(
                        func=ast.Name(id=inner_resolved.annotation_expr),
                        args=[],
                        keywords=[],
                    ),
                    generators=[
                        ast.comprehension(
                            target=ast.Name(id="_"),
                            iter=ast.Call(
                                func=ast.Name(id="range"),
                                args=[ast.Constant(value=size)],
                                keywords=[],
                            ),
                            ifs=[],
                            is_async=0,
                        )
                    ],
                )
            ],
            keywords=[],
        )
    zero = _zero_node(inner)
    if zero is None:
        raise ValueError(f"{context}: unsupported fixed-array element type")
    return ast.BinOp(
        left=ast.Tuple(elts=[zero], ctx=ast.Load()),
        op=ast.Mult(),
        right=ast.Constant(value=size),
    )


__all__ = ["_container_default"]
