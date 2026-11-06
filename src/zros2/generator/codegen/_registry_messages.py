"""Message registry section for the generated runtime registry."""

import ast


def _reg_message_section() -> list[ast.stmt]:
    """``_TYPES`` dict + ``register`` / ``get_type`` / ``has_type`` / ``iter_types``."""
    _str = ast.Name(id="str")
    _type = ast.Name(id="type")
    _none = ast.Constant(value=None)
    _type_rosmsg = ast.Subscript(value=_type, slice=ast.Name(id="RosMessage"))

    return [
        # _TYPES: dict[str, type[RosMessage]] = {}
        ast.AnnAssign(
            target=ast.Name(id="_TYPES"),
            annotation=ast.Subscript(
                value=ast.Name(id="dict"),
                slice=ast.Tuple(elts=[_str, _type_rosmsg]),
            ),
            value=ast.Dict(keys=[], values=[]),
            simple=1,
        ),
        # register(cls, full_name) -> None
        ast.FunctionDef(
            name="register",
            args=ast.arguments(
                posonlyargs=[],
                args=[
                    ast.arg(arg="cls", annotation=_type_rosmsg),
                    ast.arg(arg="full_name", annotation=_str),
                ],
                kwonlyargs=[],
                kw_defaults=[],
                defaults=[],
            ),
            body=[
                ast.Expr(
                    value=ast.Constant(
                        value="Register a message/service/action class for runtime lookup.",
                    )
                ),
                ast.Assign(
                    targets=[
                        ast.Subscript(
                            value=ast.Name(id="_TYPES"),
                            slice=ast.Name(id="full_name"),
                        )
                    ],
                    value=ast.Name(id="cls"),
                ),
            ],
            decorator_list=[],
            returns=_none,
        ),
        # get_type(name) -> type[RosMessage]
        ast.FunctionDef(
            name="get_type",
            args=ast.arguments(
                posonlyargs=[],
                args=[ast.arg(arg="name", annotation=_str)],
                kwonlyargs=[],
                kw_defaults=[],
                defaults=[],
            ),
            body=[
                ast.Expr(
                    value=ast.Constant(
                        value="Look up a type by its fully qualified name.",
                    )
                ),
                ast.If(
                    test=ast.UnaryOp(
                        op=ast.Not(),
                        operand=ast.Compare(
                            left=ast.Name(id="name"),
                            ops=[ast.In()],
                            comparators=[ast.Name(id="_TYPES")],
                        ),
                    ),
                    body=[
                        ast.Expr(
                            value=ast.Call(
                                func=ast.Name(id="_raise_not_found"),
                                args=[ast.Name(id="name"), ast.Name(id="_TYPES")],
                                keywords=[],
                            )
                        )
                    ],
                    orelse=[],
                ),
                ast.Return(
                    value=ast.Subscript(
                        value=ast.Name(id="_TYPES"),
                        slice=ast.Name(id="name"),
                    )
                ),
            ],
            decorator_list=[],
            returns=_type_rosmsg,
        ),
        # has_type(name) -> bool
        ast.FunctionDef(
            name="has_type",
            args=ast.arguments(
                posonlyargs=[],
                args=[ast.arg(arg="name", annotation=_str)],
                kwonlyargs=[],
                kw_defaults=[],
                defaults=[],
            ),
            body=[
                ast.Expr(
                    value=ast.Constant(
                        value="Check whether a type is registered.",
                    )
                ),
                ast.Return(
                    value=ast.Compare(
                        left=ast.Name(id="name"),
                        ops=[ast.In()],
                        comparators=[ast.Name(id="_TYPES")],
                    )
                ),
            ],
            decorator_list=[],
            returns=ast.Name(id="bool"),
        ),
        # iter_types() -> list[str]
        ast.FunctionDef(
            name="iter_types",
            args=ast.arguments(
                posonlyargs=[],
                args=[],
                kwonlyargs=[],
                kw_defaults=[],
                defaults=[],
            ),
            body=[
                ast.Expr(
                    value=ast.Constant(
                        value="Return a sorted list of all registered type names.",
                    )
                ),
                ast.Return(
                    value=ast.Call(
                        func=ast.Name(id="sorted"),
                        args=[ast.Name(id="_TYPES")],
                        keywords=[],
                    )
                ),
            ],
            decorator_list=[],
            returns=ast.Subscript(
                value=ast.Name(id="list"),
                slice=_str,
            ),
        ),
    ]




__all__ = ["_reg_message_section"]
