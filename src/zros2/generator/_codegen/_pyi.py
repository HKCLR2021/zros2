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
import re

from .._parser import MsgDefinition, MsgField
from .._type_map import resolve_type
from .._utilities import _generated_metadata_stmts, _header_comment, _default_expr


def _stub_annotation(expr: str) -> str:
    """Translate a CDR annotation expression into a native Python type hint.

    ``msg_def`` fields carry CDR-level type expressions (e.g.
    ``sequence[int16]``, ``array[float64, 3]``, ``bounded_str[128]``).
    This function rewrites those into the equivalent pure-Python
    annotation so that type checkers understand them without any
    CDR-aware plugin.

    The mapping is deliberately lossy when CDR and Python don't align
    perfectly (e.g. all integer widths collapse to ``int``,
    bounded strings become plain ``str``).  This is fine for static
    analysis because the *runtime* module still enforces the CDR
    constraints; the stub only needs to describe the shape.
    """
    expr = re.sub(r'^sequence\[(.+)\]$', r'Sequence[\1]', expr)
    expr = re.sub(r'^array\[(.+),\s*\d+\]$', r'tuple[\1, ...]', expr)
    expr = re.sub(r'^bounded_str\[\d+\]$', 'str', expr)

    _MAPPING = {
        "int8": "int", "int16": "int", "int32": "int", "int64": "int",
        "uint8": "int", "uint16": "int", "uint32": "int", "uint64": "int",
        "float32": "float", "float64": "float",
        "bool": "bool",
        "str": "str", "string": "str", "wstring": "str",
        "byte": "int", "char": "int",
    }
    pattern = re.compile(
        r'\b(' + '|'.join(re.escape(k) for k in _MAPPING) + r')\b'
    )
    return pattern.sub(lambda m: _MAPPING[m.group(1)], expr)


def _make_stub_field(field: MsgField, defn: MsgDefinition,
                     root_package: str) -> tuple[str, str, bool]:
    """Build the annotated field line for a stub's class body.

    Returns a tuple of:
        - native    – the resolved Python annotation string
        - line      – the full ``name: type = default`` source line
        - needs_seq – whether this field references ``Sequence``
    """
    resolved = resolve_type(
        field.type_str,
        current_package=defn.package,
        root_package=root_package,
    )
    native = _stub_annotation(resolved.annotation_expr)
    needs_seq = "sequence" in resolved.annotation_expr
    default_suffix = f" = {field.default}" if field.default is not None else ""
    line = f"    {field.name}: {native}{default_suffix}"
    return native, line, needs_seq


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

    # -- Field annotations (AnnAssign nodes) -------------------------------
    for field in defn.fields:
        resolved = resolve_type(
            field.type_str,
            current_package=defn.package,
            root_package=root_package,
        )
        native = _stub_annotation(resolved.annotation_expr)
        if "sequence" in resolved.annotation_expr:
            needs_sequence = True
        if resolved.external_import:
            ext_imports.append(resolved.external_import)
        body.append(ast.AnnAssign(
            target=ast.Name(id=field.name),
            annotation=ast.parse(native, mode="eval").body,
            value=None,
            simple=1,
        ))

    # -- Constant annotations (ClassVar-wrapped) ---------------------------
    for const in defn.constants:
        resolved = resolve_type(
            const.type_str,
            current_package=defn.package,
            root_package=root_package,
        )
        native = _stub_annotation(resolved.annotation_expr)
        ext_imports.append("from typing import ClassVar")
        body.append(ast.AnnAssign(
            target=ast.Name(id=const.name),
            annotation=ast.Subscript(
                value=ast.Name(id="ClassVar"),
                slice=ast.parse(native, mode="eval").body,
            ),
            value=ast.parse(const.default, mode="eval").body if const.default else None,
            simple=1,
        ))
        if resolved.external_import:
            ext_imports.append(resolved.external_import)

    # -- __init__ signature ------------------------------------------------
    # kw_defaults MUST have the same length as kwonlyargs, otherwise
    # ast.unparse raises ValueError.  Every field defaults to None so
    # the constructor is fully keyword-optional, just like the runtime.
    init_params: list[ast.arg] = []
    for field in defn.fields:
        resolved = resolve_type(
            field.type_str,
            current_package=defn.package,
            root_package=root_package,
        )
        native = _stub_annotation(resolved.annotation_expr)
        init_params.append(ast.arg(
            arg=field.name,
            annotation=ast.parse(native, mode="eval").body,
        ))
    if init_params:
        # Use type-appropriate defaults (same logic as the runtime .py)
        # instead of ``None``, so type checkers see correct types.
        kw_defaults: list[ast.expr] = []
        for field in defn.fields:
            resolved = resolve_type(
                field.type_str,
                current_package=defn.package,
                root_package=root_package,
            )
            default_str = _default_expr(field.type_str)
            if resolved.external_import and default_str == "None":
                default_str = f"{resolved.annotation_expr}()"
            kw_defaults.append(
                ast.parse(default_str, mode="eval").body
                if default_str else ast.Constant(value=None))

        body.append(ast.FunctionDef(
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
        ))

    # -- Methods mirroring _msg.py -----------------------------------------
    body.append(ast.FunctionDef(
        name="serialize",
        args=ast.arguments(
            posonlyargs=[], args=[ast.arg(arg="self")],
            kwonlyargs=[], kw_defaults=[], defaults=[],
        ),
        body=[ast.Expr(value=ast.Constant(value=Ellipsis))],
        decorator_list=[],
        returns=ast.Name(id="bytes"),
    ))

    body.append(ast.FunctionDef(
        name="deserialize",
        args=ast.arguments(
            posonlyargs=[],
            args=[ast.arg(arg="cls"), ast.arg(arg="data", annotation=ast.Name(id="bytes"))],
            kwonlyargs=[], kw_defaults=[], defaults=[],
        ),
        body=[ast.Expr(value=ast.Constant(value=Ellipsis))],
        decorator_list=[ast.Name(id="classmethod")],
        returns=return_annotation,
    ))

    body.append(ast.FunctionDef(
        name="from_dict",
        args=ast.arguments(
            posonlyargs=[],
            args=[
                ast.arg(arg="cls"),
                ast.arg(arg="data", annotation=ast.Subscript(
                    value=ast.Name(id="dict"),
                    slice=ast.Tuple(elts=[ast.Name(id="str"), ast.Name(id="object")]),
                )),
            ],
            kwonlyargs=[], kw_defaults=[], defaults=[],
        ),
        body=[ast.Expr(value=ast.Constant(value=Ellipsis))],
        decorator_list=[ast.Name(id="classmethod")],
        returns=return_annotation,
    ))

    body.append(ast.FunctionDef(
        name="from_attributes",
        args=ast.arguments(
            posonlyargs=[],
            args=[
                ast.arg(arg="cls"),
                ast.arg(arg="obj", annotation=ast.Name(id="Any")),
            ],
            kwonlyargs=[], kw_defaults=[], defaults=[],
        ),
        body=[ast.Expr(value=ast.Constant(value=Ellipsis))],
        decorator_list=[ast.Name(id="classmethod")],
        returns=return_annotation,
    ))

    body.append(ast.FunctionDef(
        name="to_dict",
        args=ast.arguments(
            posonlyargs=[], args=[ast.arg(arg="self")],
            kwonlyargs=[], kw_defaults=[], defaults=[],
        ),
        body=[ast.Expr(value=ast.Constant(value=Ellipsis))],
        decorator_list=[],
        returns=ast.Subscript(
            value=ast.Name(id="dict"),
            slice=ast.Tuple(elts=[ast.Name(id="str"), ast.Name(id="object")]),
        ),
    ))

    # -- Collect all imports -----------------------------------------------
    if needs_sequence:
        ext_imports.append("from collections.abc import Sequence")
    ext_imports.append("from typing import Any")
    ext_imports = sorted(set(ext_imports))

    # -- Assemble the module AST -------------------------------------------
    module_stmts: list[ast.stmt] = []
    module_stmts.append(ast.Expr(value=ast.Constant(
        value=f"Stub for {defn.full_name}.",
    )))

    for imp in sorted(set(ext_imports)):
        if not imp.startswith("from typing import ClassVar"):
            module_stmts.extend(ast.parse(imp).body)
    if any("ClassVar" in s for s in ext_imports):
        module_stmts.append(ast.ImportFrom(
            module="typing",
            names=[ast.alias(name="ClassVar")],
            level=0,
        ))

    # ── Module-level metadata (after imports, before class) ────────────
    source = f"{defn.package}/{defn.type_kind}/{class_name}.{defn.type_kind}"
    module_stmts.extend(_generated_metadata_stmts(source))

    module_stmts.append(ast.ClassDef(
        name=class_name,
        bases=[], keywords=[],
        body=body,
        decorator_list=[],
    ))

    full_module = ast.fix_missing_locations(ast.Module(
        body=module_stmts, type_ignores=[],
    ))

    content = ast.unparse(full_module)
    return _header_comment(content, distro=distro) + content
