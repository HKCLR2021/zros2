"""Service registry section for the generated runtime registry."""

import ast


def _reg_service_section() -> list[ast.stmt]:
    """``_SERVICES`` + ``register_service`` / ``get_service``."""
    _str = ast.Name(id="str")
    _none = ast.Constant(value=None)
    _dict_str_svc = ast.Subscript(
        value=ast.Name(id="dict"),
        slice=ast.Tuple(elts=[_str, ast.Name(id="ServiceTypes")]),
    )

    return [
        # _SERVICES: dict[str, ServiceTypes] = {}
        ast.AnnAssign(
            target=ast.Name(id="_SERVICES"),
            annotation=_dict_str_svc,
            value=ast.Dict(keys=[], values=[]),
            simple=1,
        ),
        # register_service(svc, full_name) -> None
        ast.FunctionDef(
            name="register_service",
            args=ast.arguments(
                posonlyargs=[],
                args=[
                    ast.arg(arg="svc", annotation=ast.Name(id="ServiceTypes")),
                    ast.arg(arg="full_name", annotation=_str),
                ],
                kwonlyargs=[],
                kw_defaults=[],
                defaults=[],
            ),
            body=[
                ast.Expr(
                    value=ast.Constant(
                        value="Register a service type container.",
                    )
                ),
                ast.Assign(
                    targets=[
                        ast.Subscript(
                            value=ast.Name(id="_SERVICES"),
                            slice=ast.Name(id="full_name"),
                        )
                    ],
                    value=ast.Name(id="svc"),
                ),
            ],
            decorator_list=[],
            returns=_none,
        ),
        # get_service(name) -> ServiceTypes
        ast.FunctionDef(
            name="get_service",
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
                        value="Look up a service type container by its fully qualified name.",
                    )
                ),
                ast.If(
                    test=ast.UnaryOp(
                        op=ast.Not(),
                        operand=ast.Compare(
                            left=ast.Name(id="name"),
                            ops=[ast.In()],
                            comparators=[ast.Name(id="_SERVICES")],
                        ),
                    ),
                    body=[
                        ast.Expr(
                            value=ast.Call(
                                func=ast.Name(id="_raise_not_found"),
                                args=[ast.Name(id="name"), ast.Name(id="_SERVICES")],
                                keywords=[],
                            )
                        )
                    ],
                    orelse=[],
                ),
                ast.Return(
                    value=ast.Subscript(
                        value=ast.Name(id="_SERVICES"),
                        slice=ast.Name(id="name"),
                    )
                ),
            ],
            decorator_list=[],
            returns=ast.Name(id="ServiceTypes"),
        ),
    ]




__all__ = ["_reg_service_section"]
