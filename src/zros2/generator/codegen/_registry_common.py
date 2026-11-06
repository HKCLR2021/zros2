"""Shared header/helper sections for the generated runtime registry."""

import ast


def _reg_header() -> list[ast.stmt]:
    """Module docstring + imports."""
    return [
        ast.Expr(
            value=ast.Constant(
                value=(
                    "Runtime type registry — look up message/service/action "
                    "types by string name."
                ),
            )
        ),
        ast.ImportFrom(module="typing", names=[ast.alias(name="Any")], level=0),
        ast.ImportFrom(
            module="zros2.types",
            names=[
                ast.alias(name="ServiceTypes"),
                ast.alias(name="ActionTypes"),
                ast.alias(name="RosMessage"),
            ],
            level=0,
        ),
    ]




def _reg_helper() -> list[ast.stmt]:
    """``_raise_not_found`` helper function."""
    _str = ast.Name(id="str")
    _none = ast.Constant(value=None)

    return [
        ast.FunctionDef(
            name="_raise_not_found",
            args=ast.arguments(
                posonlyargs=[],
                args=[
                    ast.arg(arg="name", annotation=_str),
                    ast.arg(
                        arg="registry",
                        annotation=ast.BinOp(
                            left=ast.Name(id="dict"),
                            op=ast.BitOr(),
                            right=ast.Constant(value=None),
                        ),
                    ),
                ],
                kwonlyargs=[],
                kw_defaults=[],
                defaults=[],
            ),
            body=[
                ast.Expr(
                    value=ast.Constant(
                        value="Raise a ``KeyError`` with a human-readable message.",
                    )
                ),
                # if registry is None: registry = _TYPES
                ast.If(
                    test=ast.Compare(
                        left=ast.Name(id="registry"),
                        ops=[ast.Is()],
                        comparators=[ast.Constant(value=None)],
                    ),
                    body=[
                        ast.Assign(
                            targets=[ast.Name(id="registry")],
                            value=ast.Name(id="_TYPES"),
                        )
                    ],
                    orelse=[],
                ),
                # available = sorted(registry)
                ast.Assign(
                    targets=[ast.Name(id="available")],
                    value=ast.Call(
                        func=ast.Name(id="sorted"),
                        args=[ast.Name(id="registry")],
                        keywords=[],
                    ),
                ),
                # Build f-string message
                ast.Assign(
                    targets=[ast.Name(id="msg")],
                    value=ast.JoinedStr(
                        values=[
                            ast.Constant(value="Type '"),
                            ast.FormattedValue(
                                value=ast.Name(id="name"), conversion=-1
                            ),
                            ast.Constant(
                                value="' is not registered. Available types ("
                            ),
                            ast.FormattedValue(
                                value=ast.Call(
                                    func=ast.Name(id="len"),
                                    args=[ast.Name(id="available")],
                                    keywords=[],
                                ),
                                conversion=-1,
                            ),
                            ast.Constant(value="): "),
                            ast.FormattedValue(
                                value=ast.Call(
                                    func=ast.Name(id="', '.join"),
                                    args=[
                                        ast.Subscript(
                                            value=ast.Name(id="available"),
                                            slice=ast.Slice(
                                                lower=None,
                                                upper=ast.Constant(value=10),
                                                step=None,
                                            ),
                                        ),
                                    ],
                                    keywords=[],
                                ),
                                conversion=-1,
                            ),
                        ]
                    ),
                ),
                # If more than 10 registered names, append "..."
                ast.If(
                    test=ast.Compare(
                        left=ast.Call(
                            func=ast.Name(id="len"),
                            args=[ast.Name(id="available")],
                            keywords=[],
                        ),
                        ops=[ast.Gt()],
                        comparators=[ast.Constant(value=10)],
                    ),
                    body=[
                        ast.AugAssign(
                            target=ast.Name(id="msg"),
                            op=ast.Add(),
                            value=ast.Constant(value="..."),
                        )
                    ],
                    orelse=[],
                ),
                # raise KeyError(msg)
                ast.Raise(
                    exc=ast.Call(
                        func=ast.Name(id="KeyError"),
                        args=[ast.Name(id="msg")],
                        keywords=[],
                    ),
                    cause=None,
                ),
            ],
            decorator_list=[],
            returns=_none,
        ),
    ]




__all__ = ["_reg_header", "_reg_helper"]
