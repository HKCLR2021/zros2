"""Action registry section for the generated runtime registry."""

import ast


def _reg_action_section() -> list[ast.stmt]:
    """``_ACTIONS`` + ``register_action`` / ``get_action``."""
    _str = ast.Name(id="str")
    _none = ast.Constant(value=None)
    _dict_str_act = ast.Subscript(
        value=ast.Name(id="dict"),
        slice=ast.Tuple(elts=[_str, ast.Name(id="ActionTypes")]),
    )

    return [
        # _ACTIONS: dict[str, ActionTypes] = {}
        ast.AnnAssign(
            target=ast.Name(id="_ACTIONS"),
            annotation=_dict_str_act,
            value=ast.Dict(keys=[], values=[]),
            simple=1,
        ),
        # register_action(act, full_name) -> None
        ast.FunctionDef(
            name="register_action",
            args=ast.arguments(
                posonlyargs=[],
                args=[
                    ast.arg(arg="act", annotation=ast.Name(id="ActionTypes")),
                    ast.arg(arg="full_name", annotation=_str),
                ],
                kwonlyargs=[],
                kw_defaults=[],
                defaults=[],
            ),
            body=[
                ast.Expr(
                    value=ast.Constant(
                        value="Register an action type container.",
                    )
                ),
                ast.Assign(
                    targets=[
                        ast.Subscript(
                            value=ast.Name(id="_ACTIONS"),
                            slice=ast.Name(id="full_name"),
                        )
                    ],
                    value=ast.Name(id="act"),
                ),
            ],
            decorator_list=[],
            returns=_none,
        ),
        # get_action(name) -> ActionTypes
        ast.FunctionDef(
            name="get_action",
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
                        value="Look up an action type container by its fully qualified name.",
                    )
                ),
                ast.If(
                    test=ast.UnaryOp(
                        op=ast.Not(),
                        operand=ast.Compare(
                            left=ast.Name(id="name"),
                            ops=[ast.In()],
                            comparators=[ast.Name(id="_ACTIONS")],
                        ),
                    ),
                    body=[
                        ast.Expr(
                            value=ast.Call(
                                func=ast.Name(id="_raise_not_found"),
                                args=[ast.Name(id="name"), ast.Name(id="_ACTIONS")],
                                keywords=[],
                            )
                        )
                    ],
                    orelse=[],
                ),
                ast.Return(
                    value=ast.Subscript(
                        value=ast.Name(id="_ACTIONS"),
                        slice=ast.Name(id="name"),
                    )
                ),
            ],
            decorator_list=[],
            returns=ast.Name(id="ActionTypes"),
        ),
    ]




__all__ = ["_reg_action_section"]
