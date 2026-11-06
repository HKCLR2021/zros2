"""
Generate ``.pyi`` stub files for static type checkers.

A ``.pyi`` stub declares the exact same interface as the ``_msg.py`` runtime module
but replaces the CDR-annotated types (e.g. ``int16``, ``sequence[float64]``,
``bounded_str[256]``) with native Python type hints (``int``, ``Sequence[float]``,
``str``).  This lets tools such as mypy, pyright, and jedi understand the
generated messages without needing the ``pycdr2`` library, which is only
available at runtime.

Why the method list mirrors ``_msg.py``
    The generated ``_msg.py`` includes ``serialize``, ``deserialize``,
    ``from_dict``, ``from_attributes``, and ``to_dict``.  Because the
    ``.pyi`` file is a type-level shadow of the real module, it must
    re-declare every member—including these methods — so type checkers
    see the same public surface.

Why ``ast`` instead of f-strings
    The companion ``_msg.py`` codegen also uses the ``ast`` module
    (not string templates) to build class bodies.  By sharing the same
    approach we keep both codegen paths structurally aligned, making it
    straightforward to verify that the stub and the runtime module stay
    in sync.  String-based approaches would drift more easily when
    signatures or field layouts change.

Why ``kw_defaults`` must match ``kwonlyargs`` length
    Python's own ``ast`` validation requires that every keyword-only
    argument in ``kwonlyargs`` has a corresponding entry in
    ``kw_defaults``; the two lists must be equal in length or
    ``ast.unparse`` raises ``ValueError``.  Because we want every
    ``__init__`` parameter to be optional (users construct messages
    positionally or via keyword), we provide ``None`` for each one.
"""

import ast

from zros2.generator.parsing._models import MsgDefinition
from zros2.generator.parsing._types import parse_type
from zros2.generator.semantics._literal_values import default_scalar, parse_literal
from zros2.generator.semantics._native_types import (
    CONTAINER_KINDS,
    native_stub_type,
    stub_annotation,
)
from zros2.generator.semantics._resolve_types import resolve_type
from zros2.generator.semantics._type_context import constant_int_map
from zros2.generator.semantics._utilities import header_comment

from ._literal_ast import literal_ast
from ._metadata import generated_metadata_stmts


def generate_stub_module(
    defn: MsgDefinition,
    root_package: str = "",
    distro: str = "",
) -> str:
    """Produce the full text of a ``.pyi`` stub module for *defn*.

    Architecture
    ------------
    The generated module contains:

    1. **Imports** – ``collections.abc.Sequence`` (if needed),
       ``typing.Any``, ``typing.ClassVar`` (if any constants exist),
       and any external imports discovered by ``resolve_type``.

    2. **Class definition** with:
       - **Annotated fields** – each field gets an ``AnnAssign`` node
         with its native-Python type.  Constants are wrapped in
         ``ClassVar[...]``.
       - **``__init__``** – keyword-only constructor with a ``None``
         default for every field, matching the runtime's defaulting
         behaviour.
       - **``serialize`` / ``deserialize`` / ``from_dict`` /
         ``from_attributes`` / ``to_dict``** – exact signatures mirroring
         the ``_msg.py`` class so type checkers can verify calls.

    3. **Header comment** – prepended via ``_header_comment()``.

    Using ``ast`` nodes (rather than f-strings) keeps this codegen path
    structurally parallel to ``_msg.py``'s codegen, making it easier to
    reason about both together and less likely they'll drift.
    """
    class_name = defn.type_name.split("/")[-1].replace("-", "_")

    ext_imports: list[str] = []
    body: list[ast.stmt] = []
    needs_sequence = False
    return_annotation = ast.Name(id=class_name)

    # -- Constant annotations (ClassVar-wrapped) -----------------------------
    for const in defn.constants:
        resolved = resolve_type(
            const.type_str,
            current_package=defn.package,
            root_package=root_package,
        )
        native = stub_annotation(const.type_str, defn.package, root_package)
        info = parse_type(const.type_str)
        if const.default is None:
            raise ValueError(f"{defn.full_name}.{const.name}: missing constant value")
        value = parse_literal(
            const.default, info, f"{defn.full_name}.{const.name}"
        )
        ext_imports.append("from typing import ClassVar")
        body.append(
            ast.AnnAssign(
                target=ast.Name(id=const.name),
                annotation=ast.Subscript(
                    value=ast.Name(id="ClassVar"),
                    slice=ast.parse(native, mode="eval").body,
                ),
                value=literal_ast(value),
                simple=1,
            )
        )
        if resolved.external_import:
            ext_imports.append(resolved.external_import)

    # -- Field annotations (AnnAssign nodes) -------------------------------
    for field in defn.fields:
        resolved = resolve_type(
            field.type_str,
            current_package=defn.package,
            root_package=root_package,
            constants=constant_int_map(defn),
        )
        native, uses_sequence = native_stub_type(
            field.type_str, defn.package, root_package
        )
        if uses_sequence:
            needs_sequence = True
        if resolved.external_import:
            ext_imports.append(resolved.external_import)
        body.append(
            ast.AnnAssign(
                target=ast.Name(id=field.name),
                annotation=ast.parse(native, mode="eval").body,
                value=None,
                simple=1,
            )
        )

    # -- __ros_name__ (dunder for full ROS 2 qualified name) ----------------
    body.append(
        ast.AnnAssign(
            target=ast.Name(id="__ros_name__"),
            annotation=ast.Name(id="str"),
            value=ast.Constant(value=defn.full_name),
            simple=1,
        )
    )

    # -- __annotations__ override (mirrors _msg.py Phase 4) -----------------
    ann_keys: list[ast.expr | None] = [ast.Constant(value=f.name) for f in defn.fields]
    ann_values = [
        ast.parse(
            stub_annotation(f.type_str, defn.package, root_package), mode="eval"
        ).body
        for f in defn.fields
    ]
    body.append(
        ast.Assign(
            targets=[ast.Name(id="__annotations__")],
            value=ast.Dict(keys=ann_keys, values=ann_values),
        )
    )

    # -- Methods (mirroring _msg.py Phase 5) --------------------------------
    body.append(
        ast.FunctionDef(
            name="to_dict",
            args=ast.arguments(
                posonlyargs=[],
                args=[ast.arg(arg="self")],
                kwonlyargs=[],
                kw_defaults=[],
                defaults=[],
            ),
            body=[ast.Expr(value=ast.Constant(value=Ellipsis))],
            decorator_list=[],
            returns=ast.Subscript(
                value=ast.Name(id="dict"),
                slice=ast.Tuple(elts=[ast.Name(id="str"), ast.Name(id="Any")]),
            ),
        )
    )

    body.append(
        ast.FunctionDef(
            name="from_dict",
            args=ast.arguments(
                posonlyargs=[],
                args=[
                    ast.arg(arg="cls"),
                    ast.arg(
                        arg="data",
                        annotation=ast.Subscript(
                            value=ast.Name(id="dict"),
                            slice=ast.Tuple(
                                elts=[ast.Name(id="str"), ast.Name(id="Any")]
                            ),
                        ),
                    ),
                ],
                kwonlyargs=[],
                kw_defaults=[],
                defaults=[],
            ),
            body=[ast.Expr(value=ast.Constant(value=Ellipsis))],
            decorator_list=[ast.Name(id="classmethod")],
            returns=return_annotation,
        )
    )

    body.append(
        ast.FunctionDef(
            name="from_attributes",
            args=ast.arguments(
                posonlyargs=[],
                args=[
                    ast.arg(arg="cls"),
                    ast.arg(arg="obj", annotation=ast.Name(id="Any")),
                ],
                kwonlyargs=[],
                kw_defaults=[],
                defaults=[],
            ),
            body=[ast.Expr(value=ast.Constant(value=Ellipsis))],
            decorator_list=[ast.Name(id="classmethod")],
            returns=return_annotation,
        )
    )

    # -- serialize / deserialize (inherited from IdlStruct) ------------------
    body.append(
        ast.FunctionDef(
            name="serialize",
            args=ast.arguments(
                posonlyargs=[],
                args=[ast.arg(arg="self")],
                kwonlyargs=[],
                kw_defaults=[],
                defaults=[],
            ),
            body=[ast.Expr(value=ast.Constant(value=Ellipsis))],
            decorator_list=[],
            returns=ast.Name(id="bytes"),
        )
    )

    body.append(
        ast.FunctionDef(
            name="deserialize",
            args=ast.arguments(
                posonlyargs=[],
                args=[
                    ast.arg(arg="cls"),
                    ast.arg(arg="data", annotation=ast.Name(id="bytes")),
                ],
                kwonlyargs=[],
                kw_defaults=[],
                defaults=[],
            ),
            body=[ast.Expr(value=ast.Constant(value=Ellipsis))],
            decorator_list=[ast.Name(id="classmethod")],
            returns=return_annotation,
        )
    )

    # -- __init__ signature (last — must come after all methods) -------------
    init_params: list[ast.arg] = []
    kw_defaults: list[ast.expr | None] = []
    for field in defn.fields:
        resolved = resolve_type(
            field.type_str,
            current_package=defn.package,
            root_package=root_package,
            constants=constant_int_map(defn),
        )
        info = parse_type(field.type_str)
        native = stub_annotation(field.type_str, defn.package, root_package)
        is_container = info.kind in CONTAINER_KINDS
        is_nested = bool(resolved.external_import)
        if is_container or is_nested:
            if field.default is not None:
                raise ValueError(
                    f"{defn.full_name}.{field.name}: default values are only "
                    "supported for scalar fields"
                )
            annotation = f"{native} | None"
            default: ast.expr = ast.Constant(value=None)
        else:
            annotation = native
            if field.default is not None:
                value = parse_literal(
                    field.default, info, f"{defn.full_name}.{field.name}"
                )
                default = literal_ast(value)
            else:
                default = literal_ast(default_scalar(info))
        init_params.append(
            ast.arg(
                arg=field.name,
                annotation=ast.parse(annotation, mode="eval").body,
            )
        )
        kw_defaults.append(default)
    if init_params:

        body.append(
            ast.FunctionDef(
                name="__init__",
                args=ast.arguments(
                    posonlyargs=[],
                    args=[ast.arg(arg="self")],
                    kwonlyargs=init_params,
                    kw_defaults=kw_defaults,
                    defaults=[],
                ),
                body=[ast.Expr(value=ast.Constant(value=Ellipsis))],
                decorator_list=[],
                returns=ast.Constant(value=None),
            )
        )

    # -- Collect all imports -----------------------------------------------
    if needs_sequence:
        ext_imports.append("from collections.abc import Sequence")
    ext_imports.append("from typing import Any")
    ext_imports.append("from dataclasses import dataclass")
    ext_imports = sorted(set(ext_imports))

    # -- Assemble the module AST -------------------------------------------
    module_stmts: list[ast.stmt] = []
    module_stmts.append(
        ast.Expr(
            value=ast.Constant(
                value=f"Stub for {defn.full_name}.",
            )
        )
    )

    for imp in sorted(set(ext_imports)):
        if not imp.startswith("from typing import ClassVar"):
            module_stmts.extend(ast.parse(imp).body)
    if any("ClassVar" in s for s in ext_imports):
        module_stmts.append(
            ast.ImportFrom(
                module="typing",
                names=[ast.alias(name="ClassVar")],
                level=0,
            )
        )

    # ── Module-level metadata (after imports, before class) ────────────
    source = f"{defn.package}/{defn.type_kind}/{class_name}.{defn.type_kind}"
    module_stmts.extend(generated_metadata_stmts(source))

    module_stmts.append(
        ast.ClassDef(
            name=class_name,
            bases=[],
            keywords=[],
            body=body,
            decorator_list=[
                ast.Call(
                    func=ast.Name(id="dataclass"),
                    args=[],
                    keywords=[ast.keyword(arg="init", value=ast.Constant(False))],
                ),
            ],
        )
    )

    full_module = ast.fix_missing_locations(
        ast.Module(
            body=module_stmts,
            type_ignores=[],
        )
    )

    content = ast.unparse(full_module)
    return header_comment(content, distro=distro) + content
