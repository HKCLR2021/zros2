"""
Code generation for ROS 2 message modules.
Produces Python source for a single .py module defining a dataclass-like class
backed by pycdr2.IdlStruct for CDR serialization.
"""


import ast
import pathlib
from collections.abc import Iterator
from dataclasses import dataclass

from .._parser import MsgDefinition, MsgField
from .._type_grammar import parse_type
from .._type_map import _inner_type_str, resolve_type
from .._utilities import _default_expr, _generated_metadata_stmts, _header_comment

from lark import LarkError


# ── Data type ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class GeneratedFile:
    """Represents a file to be written to disk."""

    path: pathlib.Path
    content: str

    def __iter__(self) -> Iterator[pathlib.Path | str]:
        return iter((self.path, self.content))


# When ``root_package`` is provided (e.g. in a multi-package workspace),
# the registry lives under that package namespace, so the import becomes
# ``from <root_package>._registry import ...`` rather than a bare relative import.
def _registry_import(root_package: str) -> str:
    """Return the correct ``from ... _registry import ...`` prefix."""
    if root_package:
        return root_package + "._registry"
    return "_registry"


# pycdr2 scalar types (plus bool/str) that ROS 2 always treats as required.
# Unlike nested message types they can never be None in CDR, so wrapping
# them in Optional would change the wire format (extra presence flag).
_PYCDR2_PRIMITIVES: frozenset[str] = frozenset({
    "bool", "int8", "int16", "int32", "int64",
    "uint8", "uint16", "uint32", "uint64",
    "float32", "float64",
    "str", "byte", "char",
})


def _needs_optional_annotation(default_str: str, ann_expr: str) -> bool:
    """Whether the ``__init__`` signature needs ``Optional`` for type checkers.

    Nested types defaulting to ``None`` need ``Optional`` so static type
    checkers accept the ``None`` default.  The wrapper is applied **only**
    in the ``__init__`` signature — the class-level annotation stays bare
    because pycdr2 reads it at runtime for CDR encoding and ``Optional``
    would inject an unwanted presence flag on the wire.
    """
    return default_str == "None" and ann_expr not in _PYCDR2_PRIMITIVES


def _is_container_type(type_str: str) -> bool:
    """Check if a type string represents an array or sequence."""
    try:
        info = parse_type(type_str)
    except LarkError:
        return False
    return info.kind in (
        "unbounded_sequence", "bounded_sequence",
        "unbounded", "fixed", "bounded",
    )


# ═══════════════════════════════════════════════════════════════════════════
# Hardcoded to_dict / from_dict generation
# ═══════════════════════════════════════════════════════════════════════════
#
# These functions generate per-message ``to_dict`` and ``from_dict`` methods
# that eliminate all runtime reflection (``get_type_hints``, ``fields()``,
# ``is_dataclass``, ``getattr``).  The generator inspects ``TypeInfo.kind``
# and ``ResolvedType.external_import`` at codegen time to produce the optimal
# field-access code for each field type.


def _gen_to_dict_value(
    field: MsgField, defn: MsgDefinition, root_package: str,
) -> ast.expr:
    """Generate AST expression for a single field in a ``to_dict`` return dict.

    The path chosen depends on ``TypeInfo.kind`` (scalar vs container) and
    ``ResolvedType.external_import`` (primitive vs nested message):

    * primitive scalar          → ``self.field``
    * nested message scalar     → ``self.field.to_dict()``
    * primitive array/sequence  → ``list(self.field)``
    * nested message array/seq  → ``[e.to_dict() for e in self.field]``
    """
    info = parse_type(field.type_str)
    resolved = resolve_type(
        field.type_str, current_package=defn.package,
        root_package=root_package,
    )
    self_attr = ast.Attribute(value=ast.Name(id="self"), attr=field.name)

    # ── Container types (array / sequence) ────────────────────────────────
    if info.kind in (
        "unbounded_sequence", "bounded_sequence",
        "unbounded", "fixed", "bounded",
    ):
        inner_str = _inner_type_str(info)
        inner_resolved = resolve_type(
            inner_str, current_package=defn.package,
            root_package=root_package,
        )
        if inner_resolved.external_import:
            # Nested message array: [e.to_dict() for e in cast(list, self.field)]
            # ``cast()`` is a zero-runtime-cost hint for type checkers so they
            # accept iterating over pycdr2's ``sequence[T]`` / ``array[T, N]``.
            cast_wrapper = ast.Call(
                func=ast.Name(id="cast"),
                args=[ast.Name(id="list"), self_attr],
                keywords=[],
            )
            return ast.ListComp(
                elt=ast.Call(
                    func=ast.Attribute(
                        value=ast.Name(id="e"), attr="to_dict",
                    ),
                    args=[], keywords=[],
                ),
                generators=[ast.comprehension(
                    target=ast.Name(id="e"), iter=cast_wrapper,
                    ifs=[], is_async=0,
                )],
            )
        # Primitive array: cast(list, self.field)
        # ``cast()`` avoids a type-checker error: pycdr2's ``array[T,N]`` /
        # ``sequence[T]`` types don't type-check as ``Iterable``.
        return ast.Call(
            func=ast.Name(id="cast"),
            args=[ast.Name(id="list"), self_attr],
            keywords=[],
        )

    # ── Nested message scalar ───────────────────────────────────────────
    if resolved.external_import:
        return ast.Call(
            func=ast.Attribute(value=self_attr, attr="to_dict"),
            args=[], keywords=[],
        )

    # ── Primitive scalar ────────────────────────────────────────────────
    return self_attr



def _gen_to_dict_method(
    defn: MsgDefinition, root_package: str,
) -> ast.FunctionDef:
    """Generate a hardcoded ``def to_dict(self) -> dict[str, object]:``.

    The method body is a single ``return {key: value, ...}`` where each
    value expression is produced by ``_gen_to_dict_value``.
    """
    keys: list[ast.expr | None] = [ast.Constant(value=f.name) for f in defn.fields]
    values = [_gen_to_dict_value(f, defn, root_package) for f in defn.fields]

    return ast.FunctionDef(
        name="to_dict",
        args=ast.arguments(
            posonlyargs=[], args=[ast.arg(arg="self")],
            kwonlyargs=[], kw_defaults=[], defaults=[],
        ),
        body=[ast.Return(value=ast.Dict(keys=keys, values=values))],
        decorator_list=[],
        returns=ast.Subscript(
            value=ast.Name(id="dict"),
            slice=ast.Tuple(elts=[
                ast.Name(id="str"), ast.Name(id="Any"),
            ]),
        ),
    )



def _gen_from_dict_value(
    field: MsgField, defn: MsgDefinition, root_package: str,
) -> ast.expr:
    """Generate AST expression for a single field in a ``from_dict`` constructor call.

    Symmetric to ``_gen_to_dict_value`` but reversed:

    * primitive scalar          → ``data["field"]``
    * nested message scalar     → ``Type.from_dict(data["field"])``
    * primitive array/sequence  → ``data["field"]``
    * nested message array/seq  → ``[Type.from_dict(i) for i in data["field"]]``
    """
    info = parse_type(field.type_str)
    resolved = resolve_type(
        field.type_str, current_package=defn.package,
        root_package=root_package,
    )
    data_sub = ast.Subscript(
        value=ast.Name(id="data"),
        slice=ast.Constant(value=field.name),
    )

    # ── Container types (array / sequence) ────────────────────────────────
    if info.kind in (
        "unbounded_sequence", "bounded_sequence",
        "unbounded", "fixed", "bounded",
    ):
        inner_str = _inner_type_str(info)
        inner_resolved = resolve_type(
            inner_str, current_package=defn.package,
            root_package=root_package,
        )
        if inner_resolved.external_import:
            # Nested message array: [InnerType.from_dict(item) for item in data["field"]]
            inner_name = inner_resolved.annotation_expr
            return ast.ListComp(
                elt=ast.Call(
                    func=ast.Attribute(
                        value=ast.Name(id=inner_name), attr="from_dict",
                    ),
                    args=[ast.Name(id="item")], keywords=[],
                ),
                generators=[ast.comprehension(
                    target=ast.Name(id="item"), iter=data_sub,
                    ifs=[], is_async=0,
                )],
            )
        # Primitive array: data["field"]
        return data_sub

    # ── Nested message scalar ───────────────────────────────────────────
    if resolved.external_import:
        return ast.Call(
            func=ast.Attribute(
                value=ast.Name(id=resolved.annotation_expr),
                attr="from_dict",
            ),
            args=[data_sub], keywords=[],
        )

    # ── Primitive scalar ────────────────────────────────────────────────
    return data_sub



def _gen_from_dict_method(
    defn: MsgDefinition, root_package: str,
) -> ast.FunctionDef:
    """Generate a hardcoded ``def from_dict(cls, data) -> ClassName:``.

    The method body constructs ``ClassName(keyword=value, ...)`` where each
    value expression is produced by ``_gen_from_dict_value``.
    """
    class_name = defn.type_name.split("/")[-1].replace("-", "_")

    keywords = [
        ast.keyword(
            arg=f.name,
            value=_gen_from_dict_value(f, defn, root_package),
        )
        for f in defn.fields
    ]

    return ast.FunctionDef(
        name="from_dict",
        args=ast.arguments(
            posonlyargs=[],
            args=[
                ast.arg(arg="cls"),
                ast.arg(arg="data", annotation=ast.Subscript(
                    value=ast.Name(id="dict"),
                    slice=ast.Tuple(elts=[
                        ast.Name(id="str"), ast.Name(id="Any"),
                    ]),
                )),
            ],
            kwonlyargs=[], kw_defaults=[], defaults=[],
        ),
        body=[ast.Return(value=ast.Call(
            func=ast.Name(id=class_name),
            args=[], keywords=keywords,
        ))],
        decorator_list=[ast.Name(id="classmethod")],
        # Use string forward reference — the class name is not yet defined
        # when the class body executes.
        returns=ast.Constant(value=class_name),
    )


def generate_message_module(
    defn: MsgDefinition,
    root_package: str = "",
    distro: str = "",
) -> str:
    """Generate Python source code for a single ROS 2 message type.

    Uses ``class X(IdlStruct):`` with a hand-written
    ``__init__(self, *, …)`` because pycdr2's ``IdlMeta.__prepare__``
    interferes with ``@dataclass``-generated ``__init__`` on Python 3.12+
    (PEP 649 / ``__annotate__``).
    ``@dataclass(init=False)`` is applied for ``__repr__`` and ``__eq__``.
    """
    class_name = defn.type_name.split("/")[-1].replace("-", "_")

    if not class_name or not class_name[0].isalpha():
        raise ValueError(
            f"Invalid type_name '{defn.type_name}' — "
            f"could not derive a valid Python class name"
        )

    pycdr2_imports: set[str] = set()
    ext_imports: list[str] = []

    # ── Build the class body ─────────────────────────────────────────────
    body: list[ast.stmt] = []
    ann_keys: list[ast.expr | None] = []
    ann_values: list[ast.expr] = []
    needs_cast = False

    # ── Phase 1 — Constants ────────────────────────────────────────────
    #
    # ROS 2 IDL constants are modelled as ``ClassVar[type]`` annotations.
    # They are deliberately excluded from the ``__annotations__`` dict
    # re-assigned later because pycdr2 iterates ``__annotations__``
    # to determine which fields to CDR-encode, and ``ClassVar`` would
    # cause a runtime crash when pycdr2 tries to resolve it as a CDR type.

    for const in defn.constants:
        resolved = resolve_type(
            const.type_str,
            current_package=defn.package,
            root_package=root_package,
        )
        pycdr2_imports.update(resolved.import_names)
        if resolved.external_import:
            ext_imports.append(resolved.external_import)

        default = const.default
        if const.type_str == "bool" and default is not None:
            default = "True" if default.lower() in ("true", "1") else "False"

        body.append(ast.AnnAssign(
            target=ast.Name(id=const.name),
            annotation=ast.Subscript(
                value=ast.Name(id="ClassVar"),
                slice=ast.parse(resolved.annotation_expr, mode="eval").body,
            ),
            value=ast.parse(default, mode="eval").body if default else None,
            simple=1,
        ))

    # ── Phase 2 — Field annotations ────────────────────────────────────
    #
    # Each field produces two annotation expressions that intentionally
    # diverge:
    #
    #   * ``class_ann_expr`` — bare type (e.g. ``Point``).  This is placed
    #     in the class body and in the re-assigned ``__annotations__`` dict.
    #     pycdr2 reads ``__annotations__`` at runtime to determine CDR
    #     fields; a bare type tells it the field is always present (no
    #     Optional presence flag on the wire), which is correct for ROS 2
    #     CDR.
    #
    #   * ``ann_expr`` — wrapped in ``Optional[T]`` (e.g. ``Optional[Point]``)
    #     when the default is ``None``.  This goes into the hand-written
    #     ``__init__`` signature so static type checkers (mypy, pyright)
    #     accept ``None`` as a valid argument for the parameter.
    #
    # If we used ``Optional`` at the class level, pycdr2 would add an
    # unwanted presence flag to the CDR encoding of every instance, even
    # when the value is never actually ``None`` at runtime.
    for field in defn.fields:
        resolved = resolve_type(
            field.type_str,
            current_package=defn.package,
            root_package=root_package,
        )
        pycdr2_imports.update(resolved.import_names)
        if resolved.external_import:
            ext_imports.append(resolved.external_import)

        ann_expr = resolved.annotation_expr
        orig_default = _default_expr(field.type_str)
        needs_optional = (orig_default == "None"
                          and ann_expr not in _PYCDR2_PRIMITIVES)

        # ── Phase 2 — Default values for nested types ──────────────────
        #
        # ROS 2 CDR requires nested struct fields to always be present
        # (no Optional presence flag).  Using ``= None`` at the class
        # level would produce ``Optional[Nested]`` in the annotation,
        # adding that unwanted flag.  Instead we generate
        # ``field(default_factory=Nested)``, which gives a fresh empty
        # instance on construction.
        #
        # Two reasons we use ``default_factory`` over ``= Nested()``:
        #   (a) ``@dataclass(init=False)`` with CPython 3.12+ eagerly
        #       evaluates default values and rejects mutable defaults
        #       like ``Point()`` with a ``ValueError``.
        #   (b) ``default_factory`` defers construction to call time,
        #       avoiding shared-mutable-instance bugs.
        if resolved.external_import and needs_optional:
            default_str = f"{ann_expr}()"
        else:
            default_str = orig_default

        # Class-level annotation: bare type (never Optional).
        # pycdr2 reads this for CDR encoding; ``Optional`` would inject an
        # unwanted presence flag.  The ``__init__`` signature gets the
        # Optional wrapper so type checkers accept ``None`` defaults.
        class_ann_expr = ann_expr

        # ``field(default_factory=ClassName)`` for nested types defaulting to
        # an empty instance: ``@dataclass(init=False)`` rejects mutable default
        # values, and the factory gives a fresh instance each call.
        if default_str and default_str.endswith("()") and len(default_str) > 2:
            factory_cls = default_str[:-2]
            body.append(ast.AnnAssign(
                target=ast.Name(id=field.name),
                annotation=ast.parse(class_ann_expr, mode="eval").body,
                value=ast.Call(
                    func=ast.Name(id="field"),
                    args=[],
                    keywords=[
                        ast.keyword(arg="default_factory",
                                    value=ast.Name(id=factory_cls)),
                    ],
                ),
                simple=1,
            ))
        else:
            # For pycdr2 sequence/array types, wrap the tuple default in
            # ``cast()`` so pyright accepts it at the class level.
            if default_str and default_str != "None" and (
                class_ann_expr.startswith("sequence[")
                or class_ann_expr.startswith("array[")
            ):
                needs_cast = True
                body.append(ast.AnnAssign(
                    target=ast.Name(id=field.name),
                    annotation=ast.parse(class_ann_expr, mode="eval").body,
                    value=ast.Call(
                        func=ast.Name(id="cast"),
                        args=[
                            ast.parse(class_ann_expr, mode="eval").body,
                            ast.parse(default_str, mode="eval").body,
                        ],
                        keywords=[],
                    ),
                    simple=1,
                ))
            else:
                body.append(ast.AnnAssign(
                    target=ast.Name(id=field.name),
                    annotation=ast.parse(class_ann_expr, mode="eval").body,
                    value=(ast.parse(default_str, mode="eval").body
                           if default_str else None),
                    simple=1,
                ))

        # Record field name + type for the ``__annotations__`` override
        # below (Phase 4).  These entries are what pycdr2 reads to determine
        # the CDR encoding of each field.
        ann_keys.append(ast.Constant(value=field.name))
        ann_values.append(ast.parse(class_ann_expr, mode="eval").body)

        # __init__ param annotation gets Optional for type checkers
        if needs_optional:
            ann_expr = f"Optional[{ann_expr}]"

    # ── Phase 2 — __ros_name__ ──────────────────────────────────────────
    #
    # Every generated message class carries its fully-qualified ROS 2 name
    # (e.g. "std_msgs/msg/String") so that runtime code can introspect the
    # ROS type without external lookup.
    body.append(ast.AnnAssign(
        target=ast.Name(id="__ros_name__"),
        annotation=ast.Name(id="str"),
        value=ast.Constant(value=defn.full_name),
        simple=1,
    ))

    # ── Phase 4 — ``__annotations__`` override ──────────────────────────
    #
    # pycdr2's metaclass ``IdlMeta.__prepare__`` consumes the annotation
    # dict entries injected by ``AnnAssign`` during class body execution,
    # so by the time Python finishes building the class the per-class
    # ``__annotations__`` dict is empty.  Static analysers (mypy, pyright,
    # IDEs) rely on ``__annotations__`` to know field types, so we
    # re-assign it here with an explicit ``Dict[str, type]`` containing
    # only the CDR-carrying fields.  Constants are excluded — pycdr2 would
    # crash trying to resolve ``ClassVar`` as a CDR type.
    body.append(ast.Assign(
        targets=[ast.Name(id="__annotations__")],
        value=ast.Dict(keys=ann_keys, values=ann_values),
    ))

    # ── Phase 5 — Built-in methods ─────────────────────────────────────
    #
    # ``to_dict`` and ``from_dict`` are hardcoded at generation time,
    # eliminating all runtime reflection.  ``from_attributes`` still delegates
    # to a utility function because the source object's shape is unknown
    # until runtime.
    body.append(_gen_to_dict_method(defn, root_package))
    body.append(_gen_from_dict_method(defn, root_package))

    body.append(ast.FunctionDef(
        name="from_attributes",
        args=ast.arguments(
            posonlyargs=[],
            args=[
                ast.arg(arg="cls", annotation=ast.Subscript(
                        value=ast.Name(id="type"),
                        slice=ast.Constant(value=class_name),
                    )),
                ast.arg(arg="obj",
                        annotation=ast.Name(id="Any")),
            ],
            kwonlyargs=[],
            kw_defaults=[],
            defaults=[],
        ),
        body=[
            ast.Return(value=ast.Call(
                func=ast.Name(id="_from_attributes"),
                args=[ast.Name(id="cls"), ast.Name(id="obj")],
                keywords=[],
            )),
        ],
        decorator_list=[ast.Name(id="classmethod")],
        returns=None,
    ))

    # ── Phase 6 — Hand-written ``__init__`` ────────────────────────────
    #
    # ``@dataclass(init=False)`` means we must provide ``__init__``
    # ourselves.  The signature uses keyword-only args:
    #
    #     def __init__(self, *, field: type = default) -> None: ...
    #
    # Keyword-only avoids positional-ordering bugs in auto-generated
    # wrappers and keeps the constructor self-documenting.
    #
    # Why not let ``@dataclass`` generate ``__init__``?
    # ``IdlMeta.__prepare__`` (pycdr2's metaclass) returns a namespace
    # that is not a plain ``dict``.  On Python 3.12+, dataclass's
    # ``__init__`` generator (influenced by PEP 649 / ``__annotate__``)
    # can fail or misbehave with a non-dict namespace.  A hand-written
    # ``__init__`` is simple and reliable.
    #
    # The field iteration duplicates Phase 1 — we need the resolved types
    # and defaults again because the ``__init__`` signature uses the
    # ``Optional``-wrapped annotation (for type checkers) while the class
    # body uses the bare annotation (for pycdr2).

    kwonlyargs: list[ast.arg] = []
    kw_defaults: list[ast.expr | None] = []
    init_body: list[ast.stmt] = []
    needs_optional_import = False
    for field in defn.fields:
        resolved = resolve_type(
            field.type_str,
            current_package=defn.package,
            root_package=root_package,
        )

        ann_expr = resolved.annotation_expr
        orig_default = _default_expr(field.type_str)

        # Translate pycdr2 types to Python-native equivalents for the
        # ``__init__`` signature so that static type checkers (pyright,
        # mypy) accept immutable defaults like ``()``.
        init_ann_expr = ann_expr
        if init_ann_expr.startswith("sequence["):
            # sequence[GoalStatus, 10] → Sequence[GoalStatus]
            inner = init_ann_expr[len("sequence["):-1]
            # Strip bounded length: "GoalStatus, 10" → "GoalStatus"
            if "," in inner and "[" not in inner.rsplit(",", 1)[1]:
                inner = inner.rsplit(",", 1)[0].strip()
            init_ann_expr = f"Sequence[{inner}]"
            ext_imports.append("from typing import Sequence")
        elif init_ann_expr.startswith("array["):
            # array[float64, 3] → tuple[float64, ...]
            inner = init_ann_expr[len("array["):-1]
            if "," in inner:
                inner = inner.rsplit(",", 1)[0].strip()
            init_ann_expr = f"tuple[{inner}, ...]"

        # Nested types default to an empty instance so pycdr2 always
        # serialises them as required structs, matching ROS 2 CDR.
        if resolved.external_import and orig_default == "None":
            default_str = f"{ann_expr}()"
        else:
            default_str = orig_default

        # ``Optional`` in the signature so type checkers accept ``None``
        # when the actual Python-level default is ``None`` rather than a
        # concrete instance (e.g. ``UUID()`` for nested types).
        if default_str == "None" and ann_expr not in _PYCDR2_PRIMITIVES:
            needs_optional_import = True
            init_ann_expr = f"Optional[{init_ann_expr}]"

        kwonlyargs.append(ast.arg(
            arg=field.name,
            annotation=ast.parse(init_ann_expr, mode="eval").body,
        ))
        kw_defaults.append(
            ast.parse(default_str, mode="eval").body if default_str
            else ast.Constant(value=None))

        # Wrap the body assignment in ``cast(original_type, param)`` when
        # the ``__init__`` annotation was translated to a Python-native type,
        # so pyright does not flag the assignment as a type mismatch.
        if init_ann_expr != ann_expr:
            needs_cast = True
            init_body.append(ast.Assign(
                targets=[
                    ast.Attribute(
                        value=ast.Name(id="self"), attr=field.name),
                ],
                value=ast.Call(
                    func=ast.Name(id="cast"),
                    args=[
                        ast.parse(ann_expr, mode="eval").body,
                        ast.Name(id=field.name),
                    ],
                    keywords=[],
                ),
            ))
        else:
            init_body.append(ast.Assign(
                targets=[
                    ast.Attribute(
                        value=ast.Name(id="self"), attr=field.name),
                ],
                value=ast.Name(id=field.name),
            ))
    func_def = ast.FunctionDef(
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
    body.append(func_def)

    # ── Phase 7 — ``@dataclass(init=False)`` + ``class X(IdlStruct)`` ──
    #
    # ``@dataclass(init=False)`` generates ``__repr__`` and ``__eq__`` for
    # free while skipping ``__init__`` (which we hand-write in Phase 6).
    #
    # ``IdlStruct`` (from pycdr2) provides ``serialize()`` / ``deserialize()``
    # via pycdr2's CDR machinery.  It is a plain base class — no metaclass
    # conflict because ``IdlMeta`` only becomes the metaclass of classes
    # that directly or indirectly inherit from ``IdlStruct``, and
    # ``@dataclass`` does not fight with metaclasses at the ``class``
    # statement level (it only needs a writable namespace at class-builder
    # time, which ``IdlMeta.__prepare__`` provides).
    class_def = ast.ClassDef(
        name=class_name,
        bases=[ast.Name(id="IdlStruct")],
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

    # ── Build the full module AST ────────────────────────────────────────
    module_stmts: list[ast.stmt] = []

    module_stmts.append(ast.Expr(value=ast.Constant(
        value=f'Auto-generated ROS 2 {defn.type_kind}: {defn.full_name}.',
    )))

    dc_names = [ast.alias(name="dataclass")]
    if any(isinstance(stmt, ast.AnnAssign)
           and isinstance(stmt.value, ast.Call)
           and isinstance(stmt.value.func, ast.Name)
           and stmt.value.func.id == "field"
           for stmt in body):
        dc_names.append(ast.alias(name="field"))
    module_stmts.append(ast.ImportFrom(
        module="dataclasses",
        names=dc_names,
        level=0,
    ))
    module_stmts.append(ast.ImportFrom(
        module="pycdr2",
        names=[ast.alias(name="IdlStruct")],
        level=0,
    ))
    module_stmts.append(ast.ImportFrom(
        module="zros2.types.utils",
        names=[
            ast.alias(name="from_attributes", asname="_from_attributes"),
        ],
        level=0,
    ))
    if pycdr2_imports:
        module_stmts.append(ast.ImportFrom(
            module="pycdr2.types",
            names=[ast.alias(name=n) for n in sorted(pycdr2_imports)],
            level=0,
        ))
    seen: set[str] = set()
    for imp in sorted(set(ext_imports)):
        if imp and imp not in seen:
            seen.add(imp)
            module_stmts.extend(ast.parse(imp).body)
    typing_names: list[ast.alias] = []
    if defn.constants:
        typing_names.append(ast.alias(name="ClassVar"))
    if needs_optional_import:
        typing_names.append(ast.alias(name="Optional"))
    # ``cast`` is needed for:
    #   - ``__init__`` defaults wrapping tuple→pycdr2 array (``needs_cast``)
    #   - ``to_dict`` wrapping array/sequence fields in ``cast(list, ...)``
    if needs_cast or any(_is_container_type(f.type_str) for f in defn.fields):
        typing_names.append(ast.alias(name="cast"))
    typing_names.append(ast.alias(name="Any"))
    if typing_names:
        module_stmts.append(ast.ImportFrom(
            module="typing",
            names=typing_names,
            level=0,
        ))

    # ── Module-level metadata (after imports, before class) ────────────
    source = f"{defn.package}/{defn.type_kind}/{class_name}.{defn.type_kind}"
    module_stmts.extend(_generated_metadata_stmts(source))

    module_stmts.append(class_def)

    full_module = ast.fix_missing_locations(ast.Module(
        body=module_stmts, type_ignores=[],
    ))
    content = ast.unparse(full_module)

    # ── Syntax validation ─────────────────────────────────────────────────
    # Verify the generated code is syntactically valid Python.
    try:
        compile(content, f"<{defn.full_name}>", "exec")
    except SyntaxError as exc:
        raise RuntimeError(
            f"Generated code for {defn.full_name} has syntax errors: {exc}"
        ) from exc

    return _header_comment(content, distro=distro) + content
