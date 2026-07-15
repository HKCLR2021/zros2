"""
Registry AST builder — constructs ``_registry.py`` via ``ast`` nodes.

The ``_registry.py`` module is a runtime type-lookup module that gets
bundled alongside generated message, service, and action code.  It
provides a small set of functions for registering and retrieving types
by their fully-qualified string name *without* any import-time
side-effects.

Architecture
------------
The generated module is built by concatenating several logical sections,
each produced by a ``_reg_*_section`` function:

1. **Header** — module docstring + shared imports (``typing.Any``,
   ``zros2.types.*``).

2. **Message section** — ``_TYPES`` dict + four CRUD-like functions
   (``register``, ``get_type``, ``has_type``, ``iter_types``).  This
   section is the core; all ROS 2 message types are registered here.

3. **Service section** — ``_SERVICES`` dict + ``register_service`` /
   ``get_service``.  Service types are stored separately so their
   ``ServiceTypes`` wrapper is preserved.

4. **Action section** — ``_ACTIONS`` dict + ``register_action`` /
   ``get_action``.  Analogous to the service section, but for
   ``ActionTypes`` wrappers.

5. **Helper** — ``_raise_not_found`` generates a ``KeyError`` with a
   descriptive message that lists up to ten registered names,
   truncating with ``"..."`` when there are more.

``_REGISTRY_AST`` (a module-level constant) assembles all five sections
in order and calls ``ast.fix_missing_locations`` so the resulting
``ast.Module`` is ready to be ``unparse`` d.
"""

import ast


def _reg_header() -> list[ast.stmt]:
    """Module docstring + imports."""
    return [
        ast.Expr(value=ast.Constant(
            value="Runtime type registry — look up message/service/action types by string name.",
        )),
        ast.ImportFrom(module="typing", names=[ast.alias(name="Any")], level=0),
        ast.ImportFrom(module="zros2.types", names=[
            ast.alias(name="ServiceTypes"),
            ast.alias(name="ActionTypes"),
            ast.alias(name="RosMessage"),
        ], level=0),
    ]


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
                posonlyargs=[], args=[
                    ast.arg(arg="cls", annotation=_type_rosmsg),
                    ast.arg(arg="full_name", annotation=_str),
                ],
                kwonlyargs=[], kw_defaults=[], defaults=[],
            ),
            body=[
                ast.Expr(value=ast.Constant(
                    value="Register a message/service/action class for runtime lookup.",
                )),
                ast.Assign(
                    targets=[ast.Subscript(
                        value=ast.Name(id="_TYPES"),
                        slice=ast.Name(id="full_name"),
                    )],
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
                posonlyargs=[], args=[ast.arg(arg="name", annotation=_str)],
                kwonlyargs=[], kw_defaults=[], defaults=[],
            ),
            body=[
                ast.Expr(value=ast.Constant(
                    value="Look up a type by its fully qualified name.",
                )),
                ast.If(
                    test=ast.UnaryOp(
                        op=ast.Not(),
                        operand=ast.Compare(
                            left=ast.Name(id="name"),
                            ops=[ast.In()],
                            comparators=[ast.Name(id="_TYPES")],
                        ),
                    ),
                    body=[ast.Expr(value=ast.Call(
                        func=ast.Name(id="_raise_not_found"),
                        args=[ast.Name(id="name"), ast.Name(id="_TYPES")],
                        keywords=[],
                    ))],
                    orelse=[],
                ),
                ast.Return(value=ast.Subscript(
                    value=ast.Name(id="_TYPES"),
                    slice=ast.Name(id="name"),
                )),
            ],
            decorator_list=[],
            returns=_type_rosmsg,
        ),

        # has_type(name) -> bool
        ast.FunctionDef(
            name="has_type",
            args=ast.arguments(
                posonlyargs=[], args=[ast.arg(arg="name", annotation=_str)],
                kwonlyargs=[], kw_defaults=[], defaults=[],
            ),
            body=[
                ast.Expr(value=ast.Constant(
                    value="Check whether a type is registered.",
                )),
                ast.Return(value=ast.Compare(
                    left=ast.Name(id="name"),
                    ops=[ast.In()],
                    comparators=[ast.Name(id="_TYPES")],
                )),
            ],
            decorator_list=[],
            returns=ast.Name(id="bool"),
        ),

        # iter_types() -> list[str]
        ast.FunctionDef(
            name="iter_types",
            args=ast.arguments(
                posonlyargs=[], args=[],
                kwonlyargs=[], kw_defaults=[], defaults=[],
            ),
            body=[
                ast.Expr(value=ast.Constant(
                    value="Return a sorted list of all registered type names.",
                )),
                ast.Return(value=ast.Call(
                    func=ast.Name(id="sorted"),
                    args=[ast.Name(id="_TYPES")],
                    keywords=[],
                )),
            ],
            decorator_list=[],
            returns=ast.Subscript(
                value=ast.Name(id="list"),
                slice=_str,
            ),
        ),
    ]


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
                posonlyargs=[], args=[
                    ast.arg(arg="svc", annotation=ast.Name(id="ServiceTypes")),
                    ast.arg(arg="full_name", annotation=_str),
                ],
                kwonlyargs=[], kw_defaults=[], defaults=[],
            ),
            body=[
                ast.Expr(value=ast.Constant(
                    value="Register a service type container.",
                )),
                ast.Assign(
                    targets=[ast.Subscript(
                        value=ast.Name(id="_SERVICES"),
                        slice=ast.Name(id="full_name"),
                    )],
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
                posonlyargs=[], args=[ast.arg(arg="name", annotation=_str)],
                kwonlyargs=[], kw_defaults=[], defaults=[],
            ),
            body=[
                ast.Expr(value=ast.Constant(
                    value="Look up a service type container by its fully qualified name.",
                )),
                ast.If(
                    test=ast.UnaryOp(
                        op=ast.Not(),
                        operand=ast.Compare(
                            left=ast.Name(id="name"),
                            ops=[ast.In()],
                            comparators=[ast.Name(id="_SERVICES")],
                        ),
                    ),
                    body=[ast.Expr(value=ast.Call(
                        func=ast.Name(id="_raise_not_found"),
                        args=[ast.Name(id="name"), ast.Name(id="_SERVICES")],
                        keywords=[],
                    ))],
                    orelse=[],
                ),
                ast.Return(value=ast.Subscript(
                    value=ast.Name(id="_SERVICES"),
                    slice=ast.Name(id="name"),
                )),
            ],
            decorator_list=[],
            returns=ast.Name(id="ServiceTypes"),
        ),
    ]


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
                posonlyargs=[], args=[
                    ast.arg(arg="act", annotation=ast.Name(id="ActionTypes")),
                    ast.arg(arg="full_name", annotation=_str),
                ],
                kwonlyargs=[], kw_defaults=[], defaults=[],
            ),
            body=[
                ast.Expr(value=ast.Constant(
                    value="Register an action type container.",
                )),
                ast.Assign(
                    targets=[ast.Subscript(
                        value=ast.Name(id="_ACTIONS"),
                        slice=ast.Name(id="full_name"),
                    )],
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
                posonlyargs=[], args=[ast.arg(arg="name", annotation=_str)],
                kwonlyargs=[], kw_defaults=[], defaults=[],
            ),
            body=[
                ast.Expr(value=ast.Constant(
                    value="Look up an action type container by its fully qualified name.",
                )),
                ast.If(
                    test=ast.UnaryOp(
                        op=ast.Not(),
                        operand=ast.Compare(
                            left=ast.Name(id="name"),
                            ops=[ast.In()],
                            comparators=[ast.Name(id="_ACTIONS")],
                        ),
                    ),
                    body=[ast.Expr(value=ast.Call(
                        func=ast.Name(id="_raise_not_found"),
                        args=[ast.Name(id="name"), ast.Name(id="_ACTIONS")],
                        keywords=[],
                    ))],
                    orelse=[],
                ),
                ast.Return(value=ast.Subscript(
                    value=ast.Name(id="_ACTIONS"),
                    slice=ast.Name(id="name"),
                )),
            ],
            decorator_list=[],
            returns=ast.Name(id="ActionTypes"),
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
                posonlyargs=[], args=[
                    ast.arg(arg="name", annotation=_str),
                    ast.arg(arg="registry", annotation=ast.BinOp(
                        left=ast.Name(id="dict"),
                        op=ast.BitOr(),
                        right=ast.Constant(value=None),
                    )),
                ],
                kwonlyargs=[], kw_defaults=[], defaults=[],
            ),
            body=[
                ast.Expr(value=ast.Constant(
                    value="Raise a ``KeyError`` with a human-readable message.",
                )),
                # if registry is None: registry = _TYPES
                ast.If(
                    test=ast.Compare(
                        left=ast.Name(id="registry"),
                        ops=[ast.Is()],
                        comparators=[ast.Constant(value=None)],
                    ),
                    body=[ast.Assign(
                        targets=[ast.Name(id="registry")],
                        value=ast.Name(id="_TYPES"),
                    )],
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
                    value=ast.JoinedStr(values=[
                        ast.Constant(value="Type '"),
                        ast.FormattedValue(
                            value=ast.Name(id="name"), conversion=-1),
                        ast.Constant(value="' is not registered. Available types ("),
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
                    ]),
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
                    body=[ast.AugAssign(
                        target=ast.Name(id="msg"),
                        op=ast.Add(),
                        value=ast.Constant(value="..."),
                    )],
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


# Compose the full module — assemble every section into a single ``ast.Module``.
#
# The order is significant:
#   1. Header  (docstring + imports)
#   2. Message section  (most commonly used)
#   3. Service section
#   4. Action section
#   5. Helper   (must come last; ``_raise_not_found`` references ``_TYPES``)
#
# ``ast.fix_missing_locations`` is called once so that every node gets
# proper ``lineno`` and ``col_offset`` attributes, which are required
# before ``ast.unparse`` can produce valid source code.

_REGISTRY_AST = ast.Module(
    body=(_reg_header()
          + _reg_message_section()
          + _reg_service_section()
          + _reg_action_section()
          + _reg_helper()),
    type_ignores=[],
)
ast.fix_missing_locations(_REGISTRY_AST)
