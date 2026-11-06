"""Assemble a complete message module from field plans and methods."""

import ast

from zros2.generator.codegen._literal_ast import literal_ast
from zros2.generator.codegen._metadata import generated_metadata_stmts
from zros2.generator.parsing._models import MsgDefinition
from zros2.generator.parsing._types import parse_type
from zros2.generator.semantics._literal_values import parse_literal
from zros2.generator.semantics._utilities import header_comment

from ._context import MessageContext
from ._methods import _gen_from_dict_method, _gen_to_dict_method
from ._plan import _assign, _FieldPlan, _plan_field, _type_alias


def generate_message_module(
    defn: MsgDefinition,
    root_package: str = "",
    distro: str = "",
) -> str:
    """Generate Python source code for a single ROS 2 message type."""
    ctx = MessageContext.build(defn, root_package)
    class_name = ctx.class_name
    class_token = ctx.class_token
    type_context = ctx.type_context

    pycdr2_imports: set[str] = set()
    ext_imports: list[str] = []
    module_stmts: list[ast.stmt] = []
    field_plans: list[_FieldPlan] = []

    # ── Constants ────────────────────────────────────────────────────────
    # Constants are plain class attributes in the runtime module.  The stub
    # carries ClassVar annotations for static type checkers.
    for const in defn.constants:
        info = parse_type(const.type_str)
        if const.default is None:
            raise ValueError(f"{defn.full_name}.{const.name}: missing constant value")
        value = parse_literal(
            const.default, info, f"{defn.full_name}.{const.name}"
        )
        const_node = literal_ast(value)
        field_plans.append(
            _FieldPlan(
                field=const,
                info=info,
                resolved=type_context.resolve(const.type_str),
                ann_name="",
                init_name="",
                default_name="",
                class_default=const_node,
                init_default=ast.Constant(value=None),
                init_type="",
                init_stmt=ast.Pass(),
                module_stmts=[],
                needs_field=False,
                needs_sequence=False,
            )
        )

    # ── Fields ───────────────────────────────────────────────────────────
    for index, field in enumerate(defn.fields):
        plan = _plan_field(
            field=field,
            index=index,
            defn=defn,
            root_package=root_package,
            class_token=class_token,
            type_context=type_context,
        )
        pycdr2_imports.update(plan.resolved.import_names)
        if plan.resolved.external_import:
            ext_imports.append(plan.resolved.external_import)
        for stmt in plan.module_stmts:
            module_stmts.append(stmt)
        field_plans.append(plan)

    # ── Annotations dict (module scope, never class scope) ───────────────
    annotation_items = [
        (plan.field.name, ast.Name(id=plan.ann_name))
        for plan in field_plans
        if plan.ann_name
    ]
    annotations_name = f"_ZROS2_{class_token}_ANN"
    module_stmts.append(
        _assign(
            annotations_name,
            ast.Dict(
                keys=[ast.Constant(value=name) for name, _ in annotation_items],
                values=[value for _, value in annotation_items],
            ),
        )
    )

    # ── Class body ───────────────────────────────────────────────────────
    body: list[ast.stmt] = []
    for plan in field_plans:
        if plan.ann_name:
            body.append(_assign(plan.field.name, plan.class_default))
        else:
            # Constant: plain class attribute, no annotation.  pycdr2 must not
            # see it in __annotations__.
            body.append(_assign(plan.field.name, plan.class_default))

    body.append(_assign("__ros_name__", ast.Constant(value=defn.full_name)))
    body.append(_assign("__annotations__", ast.Name(id=annotations_name)))
    body.append(_gen_to_dict_method(defn, root_package, type_context))
    body.append(_gen_from_dict_method(defn, root_package, type_context))
    body.append(
        ast.FunctionDef(
            name="from_attributes",
            args=ast.arguments(
                posonlyargs=[],
                args=[
                    ast.arg(
                        arg="cls",
                        annotation=ast.Subscript(
                            value=ast.Name(id="type"),
                            slice=ast.Constant(value=class_name),
                        ),
                    ),
                    ast.arg(arg="obj", annotation=ast.Name(id="Any")),
                ],
                kwonlyargs=[],
                kw_defaults=[],
                defaults=[],
            ),
            body=[
                ast.Return(
                    value=ast.Call(
                        func=ast.Name(id="_from_attributes"),
                        args=[ast.Name(id="cls"), ast.Name(id="obj")],
                        keywords=[],
                    )
                )
            ],
            decorator_list=[ast.Name(id="classmethod")],
            returns=None,
        )
    )

    # ── __init__ ─────────────────────────────────────────────────────────
    kwonlyargs: list[ast.arg] = []
    kw_defaults: list[ast.expr | None] = []
    init_body: list[ast.stmt] = []
    for plan in field_plans:
        if not plan.ann_name:
            continue
        module_stmts.append(_type_alias(plan.init_name, plan.init_type))
        kwonlyargs.append(
            ast.arg(arg=plan.field.name, annotation=ast.Name(id=plan.init_name))
        )
        kw_defaults.append(plan.init_default)
        init_body.append(plan.init_stmt)

    body.append(
        ast.FunctionDef(
            name="__init__",
            args=ast.arguments(
                posonlyargs=[],
                args=[ast.arg(arg="self")],
                kwonlyargs=kwonlyargs,
                kw_defaults=kw_defaults,
                defaults=[],
            ),
            body=init_body if init_body else [ast.Pass()],
            decorator_list=[],
            returns=ast.Constant(value=None),
        )
    )

    class_def = ast.ClassDef(
        name=class_name,
        bases=[ast.Name(id="IdlStruct")],
        keywords=[],
        body=body,
        decorator_list=[
            ast.Call(
                func=ast.Name(id="dataclass"),
                args=[],
                keywords=[ast.keyword(arg="init", value=ast.Constant(value=False))],
            )
        ],
    )

    # ── Imports ──────────────────────────────────────────────────────────
    header_stmts: list[ast.stmt] = [
        ast.Expr(
            value=ast.Constant(
                value=f"Auto-generated ROS 2 {defn.type_kind}: {defn.full_name}."
            )
        )
    ]

    dc_names = [ast.alias(name="dataclass")]
    if any(plan.needs_field for plan in field_plans):
        dc_names.append(ast.alias(name="field"))
    header_stmts.append(
        ast.ImportFrom(module="dataclasses", names=dc_names, level=0)
    )
    header_stmts.append(
        ast.ImportFrom(
            module="pycdr2", names=[ast.alias(name="IdlStruct")], level=0
        )
    )
    header_stmts.append(
        ast.ImportFrom(
            module="zros2.types._utils",
            names=[ast.alias(name="from_attributes", asname="_from_attributes")],
            level=0,
        )
    )
    if pycdr2_imports:
        header_stmts.append(
            ast.ImportFrom(
                module="pycdr2.types",
                names=[ast.alias(name=name) for name in sorted(pycdr2_imports)],
                level=0,
            )
        )
    seen: set[str] = set()
    for imp in sorted(set(ext_imports)):
        if imp and imp not in seen:
            seen.add(imp)
            header_stmts.extend(ast.parse(imp).body)

    typing_names: list[ast.alias] = [ast.alias(name="Any")]
    if any(plan.ann_name for plan in field_plans):
        typing_names.append(ast.alias(name="TypeAlias"))
    header_stmts.append(
        ast.ImportFrom(module="typing", names=typing_names, level=0)
    )
    if any(plan.needs_sequence for plan in field_plans):
        header_stmts.append(
            ast.ImportFrom(
                module="collections.abc", names=[ast.alias(name="Sequence")], level=0
            )
        )

    source = f"{defn.package}/{defn.type_kind}/{class_name}.{defn.type_kind}"
    full_module = ast.fix_missing_locations(
        ast.Module(
            body=header_stmts
            + generated_metadata_stmts(source)
            + module_stmts
            + [class_def],
            type_ignores=[],
        )
    )
    content = ast.unparse(full_module)

    try:
        compile(content, f"<{defn.full_name}>", "exec")
    except SyntaxError as exc:
        raise RuntimeError(
            f"Generated code for {defn.full_name} has syntax errors: {exc}"
        ) from exc

    return header_comment(content, distro=distro) + content
