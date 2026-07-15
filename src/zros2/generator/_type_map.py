"""ROS 2 type → pycdr2 type mapping.

Resolves ROS 2 type strings (as found in ``.msg`` files) to their
corresponding pycdr2 annotation expressions and Python import paths.

Type expressions are parsed via :mod:`._type_grammar` (Lark-based) instead
of regex, ensuring all valid ROS 2 syntax forms are recognised.
"""

from dataclasses import dataclass

from lark import LarkError

from ._type_grammar import ROS2_PRIMITIVE_TYPES, TypeInfo, parse_type
from ._utilities import _to_snake_case


# ═══════════════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════════════


def _inner_type_str(info: TypeInfo) -> str:
    """Reconstruct the inner (wrapped) type string from a ``TypeInfo``.

    When a type like ``string<=10[]`` is parsed, the ``TypeInfo.base_name``
    is just ``"string"`` — the bounded-string constraint is stored separately
    in ``is_bounded_string`` / ``string_max``.  This helper glues them back
    together so that recursive ``resolve_type()`` calls see the full type.
    """
    if info.is_bounded_string and info.string_max is not None:
        return f"{info.base_name}<={info.string_max}"
    if info.base_name:
        return info.base_name
    return ""


# ═══════════════════════════════════════════════════════════════════════════
# Resolved type descriptor
# ═══════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ResolvedType:
    """Result of resolving a ROS 2 type string.

    Attributes:
        annotation_expr: Python expression for the type annotation, e.g.
            ``"int32"``, ``"sequence[uint8]"``, ``"array[int32, 3]"``.
        import_names: Set of names to import from ``pycdr2.types``,
            e.g. ``{"int32", "sequence", "uint8"}``.
        external_import: A Python import statement for a nested ROS2 type,
            or ``None`` if the type is a primitive / pycdr2 built-in.
    """
    annotation_expr: str
    import_names: frozenset[str] = frozenset()
    external_import: str | None = None


# ═══════════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════════

_PRIMITIVE_MAP: dict[str, str] = {
    "bool": "bool", "byte": "uint8", "char": "uint8",
    "int8": "int8", "uint8": "uint8",
    "int16": "int16", "uint16": "uint16",
    "int32": "int32", "uint32": "uint32",
    "int64": "int64", "uint64": "uint64",
    "float32": "float32", "float64": "float64",
    "string": "str", "wstring": "str",
}

_PRIMITIVE_IMPORTS: dict[str, str] = {
    "byte": "uint8", "char": "uint8",
    "int8": "int8", "uint8": "uint8",
    "int16": "int16", "uint16": "uint16",
    "int32": "int32", "uint32": "uint32",
    "int64": "int64", "uint64": "uint64",
    "float32": "float32", "float64": "float64",
}

_PYTHON_BUILTINS: frozenset[str] = frozenset({"bool", "string", "wstring"})

_EXTERNAL_TYPES: dict[str, tuple[str, str]] = {
    "time": (
        "builtin_interfaces/msg/Time",
        "from builtin_interfaces.msg._time import Time",
    ),
    "duration": (
        "builtin_interfaces/msg/Duration",
        "from builtin_interfaces.msg._duration import Duration",
    ),
}


# ═══════════════════════════════════════════════════════════════════════════
# Resolver
# ═══════════════════════════════════════════════════════════════════════════

def resolve_type(
    type_str: str,
    current_package: str = "",
    root_package: str = "",
) -> ResolvedType:
    """Resolve a ROS 2 type string to a pycdr2 annotation expression.

    Args:
        type_str: The raw type string from the ``.msg`` file.
        current_package: The package containing the current message, used to
            resolve unqualified nested type references.
        root_package: Optional top-level package prefix for cross-module
            imports.  When set (e.g. ``"zros2_msgs"``), generated import
            statements become
            ``from zros2_msgs.std_msgs.msg.String import String``.
    """
    type_str = type_str.strip()

    try:
        info = parse_type(type_str)
    except LarkError:
        # Fall through — treat as an opaque identifier (edge case).
        info = TypeInfo(base_name=type_str)

    # Container types (array / sequence) take priority over scalar
    # checks so that e.g. ``string<=10[]`` correctly resolves to
    # ``sequence[bounded_str[10]]``.

    # ── Sequence: sequence<T> / sequence<T, N> ─────────────────────────
    if info.kind in ("unbounded_sequence", "bounded_sequence"):
        inner = resolve_type(_inner_type_str(info), current_package, root_package)
        if info.kind == "bounded_sequence" and info.array_max is not None:
            expr = f"sequence[{inner.annotation_expr}, {info.array_max}]"
        else:
            expr = f"sequence[{inner.annotation_expr}]"
        imports = set(inner.import_names) | {"sequence"}
        return _wrap(expr, imports, inner.external_import)

    # ── Array: type[] / type[N] / type[<=N] ────────────────────────────
    if info.kind in ("unbounded", "fixed", "bounded"):
        inner = resolve_type(_inner_type_str(info), current_package, root_package)

        if info.kind == "unbounded":
            expr = f"sequence[{inner.annotation_expr}]"
            imports = set(inner.import_names) | {"sequence"}
        elif info.kind == "fixed":
            expr = f"array[{inner.annotation_expr}, {info.array_size}]"
            imports = set(inner.import_names) | {"array"}
        else:  # bounded dynamic array: type[<=N] → sequence[T, N]
            expr = f"sequence[{inner.annotation_expr}, {info.array_max}]"
            imports = set(inner.import_names) | {"sequence"}

        return _wrap(expr, imports, inner.external_import)

    # ── Bounded string (scalar): string<=N / wstring<=N ────────────────
    if info.is_bounded_string:
        return ResolvedType(
            annotation_expr=f"bounded_str[{info.string_max}]",
            import_names=frozenset({"bounded_str"}),
        )

    # ── Scalar: primitives, time/duration, nested types ───────────────
    return _resolve_scalar(info.base_name, current_package, root_package)


# ═══════════════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════════════




def _resolve_scalar(name: str, current_package: str,
                    root_package: str) -> ResolvedType:
    """Resolve a scalar (non-array, non-sequence) type name."""
    # ── time / duration (aliases) ──────────────────────────────────────
    if name.lower() in _EXTERNAL_TYPES:
        full_name, import_stmt = _EXTERNAL_TYPES[name.lower()]
        short = full_name.split("/")[-1]
        return ResolvedType(annotation_expr=short, external_import=import_stmt)

    # ── Primitives ────────────────────────────────────────────────────
    if name in _PRIMITIVE_MAP:
        py_type = _PRIMITIVE_MAP[name]
        if name in _PYTHON_BUILTINS:
            return ResolvedType(py_type)
        return ResolvedType(py_type, import_names=frozenset({py_type}))

    # ── Nested / cross-package type reference ─────────────────────────
    return _resolve_nested(name, current_package, root_package)


def _resolve_nested(name: str, current_package: str,
                    root_package: str) -> ResolvedType:
    """Resolve a nested (non-primitive) type reference."""
    # Normalise to ``pkg/msg/Type`` form
    clean = name

    if "/" not in clean:
        # Unqualified → assume current_package/msg/name
        clean = f"{current_package}/msg/{name}"
    elif clean.count("/") == 1:
        # "pkg/Type" → "pkg/msg/Type"
        pkg_part, name_part = clean.split("/", 1)
        clean = f"{pkg_part}/msg/{name_part}"

    # Extract package, kind, type_name
    parts = clean.split("/")
    if len(parts) >= 3 and parts[1] in ("msg", "srv", "action"):
        pkg = parts[0]
        kind = parts[1]
        type_name = "/".join(parts[2:])
    else:
        pkg = parts[0]
        kind = "msg"
        type_name = "/".join(parts[1:])

    module_path = f"{pkg}.{kind}._{_to_snake_case(type_name)}"
    if root_package:
        module_path = f"{root_package}.{module_path}"
    import_stmt = f"from {module_path} import {type_name}"

    return ResolvedType(
        annotation_expr=type_name,
        import_names=frozenset(),
        external_import=import_stmt,
    )


def _wrap(expr: str, imports: set[str],
          external: str | None) -> ResolvedType:
    """Build a ``ResolvedType`` with or without external import."""
    if external:
        return ResolvedType(expr, frozenset(imports), external)
    return ResolvedType(expr, frozenset(imports))


# ═══════════════════════════════════════════════════════════════════════════
# Convenience
# ═══════════════════════════════════════════════════════════════════════════

def is_primitive(type_str: str) -> bool:
    """Check if a type string is a ROS 2 primitive type.

    Bounded strings (``string<=N``) return ``False`` because they are
    handled as a special pycdr2 wrapper type.
    """
    try:
        info = parse_type(type_str)
    except LarkError:
        return False

    if info.is_bounded_string:
        return False

    if info.base_name in ROS2_PRIMITIVE_TYPES:
        return True
    return info.base_name.lower() in _EXTERNAL_TYPES


# Backward-compat alias
from ._utilities import _default_expr as get_default_value  # noqa: E402,F401
