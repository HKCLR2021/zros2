"""Shared ROS type categories and native-Python type mapping.

Both the runtime renderer and the stub renderer use this module, so the
mapping from ROS primitives to ``int`` / ``float`` / ``str`` / ``bool`` lives
in exactly one place.
"""

from lark import LarkError

from zros2.generator.parsing._types import TypeInfo, parse_type

from ._resolve_types import ResolvedType, resolve_type

CONTAINER_KINDS = frozenset(
    {"unbounded_sequence", "bounded_sequence", "unbounded", "fixed", "bounded"}
)
SEQUENCE_KINDS = frozenset(
    {"unbounded_sequence", "bounded_sequence", "unbounded", "bounded"}
)
INT_TYPES = frozenset(
    {
        "int8",
        "uint8",
        "int16",
        "uint16",
        "int32",
        "uint32",
        "int64",
        "uint64",
        "byte",
        "char",
    }
)
FLOAT_TYPES = frozenset({"float32", "float64"})
STRING_TYPES = frozenset({"string", "wstring"})


def python_type(info: TypeInfo, resolved: ResolvedType) -> str:
    """Return the Python-native annotation for a scalar field type."""
    base = info.base_name
    if info.is_bounded_string or base in STRING_TYPES:
        return "str"
    if base == "bool":
        return "bool"
    if base in INT_TYPES:
        return "int"
    if base in FLOAT_TYPES:
        return "float"
    if resolved.external_import:
        return resolved.annotation_expr
    return "object"


def is_container(info: TypeInfo) -> bool:
    """Return whether *info* describes an array or sequence."""
    return info.kind in CONTAINER_KINDS




_PY_SCALARS: dict[str, str] = {
    "bool": "bool",
    **{name: "int" for name in INT_TYPES},
    **{name: "float" for name in FLOAT_TYPES},
    **{name: "str" for name in STRING_TYPES},
    "str": "str",
}


def _inner_ros_type(info: TypeInfo) -> str:
    """Rebuild the ROS type string for a TypeInfo's wrapped inner type."""
    if info.is_bounded_string and info.string_max is not None:
        return f"{info.base_name}<={info.string_max}"
    return info.base_name or ""


def native_stub_type(
    type_str: str,
    current_package: str = "",
    root_package: str = "",
) -> tuple[str, bool]:
    """Map a ROS 2 type string to a Python stub annotation.

    Returns:
        ``(annotation, needs_sequence)`` where *needs_sequence* is True
        when ``collections.abc.Sequence`` must be imported.
    """
    stripped = type_str.strip()
    if not stripped:
        return "object", False
    try:
        info = parse_type(stripped)
    except LarkError:
        return _PY_SCALARS.get(stripped, stripped), False

    if info.base_name == "wstring":
        raise ValueError(
            "wstring is not supported: ROS 2 encodes wstring as UTF-16LE, "
            "but the pycdr2 backend has no wide-string CDR type."
        )
    if info.kind in (
        "unbounded",
        "unbounded_sequence",
        "bounded",
        "bounded_sequence",
    ):
        inner, _ = native_stub_type(
            _inner_ros_type(info), current_package, root_package
        )
        return f"Sequence[{inner}]", True
    if info.kind == "fixed":
        inner, _ = native_stub_type(
            _inner_ros_type(info), current_package, root_package
        )
        return f"tuple[{inner}, ...]", False
    if info.is_bounded_string:
        return "str", False
    if info.base_name in _PY_SCALARS:
        return _PY_SCALARS[info.base_name], False
    resolved = resolve_type(
        stripped, current_package=current_package, root_package=root_package
    )
    return resolved.annotation_expr, False


def stub_annotation(
    type_str: str,
    current_package: str = "",
    root_package: str = "",
) -> str:
    """Translate a ROS 2 type string into a native Python type hint.

    The mapping is lossy when ROS and Python don't align (integer widths
    collapse to ``int``, bounded strings become ``str``).  The runtime
    module still enforces CDR constraints; the stub only describes shape.
    """
    native, _ = native_stub_type(type_str, current_package, root_package)
    return native

__all__ = [
    "CONTAINER_KINDS",
    "FLOAT_TYPES",
    "INT_TYPES",
    "SEQUENCE_KINDS",
    "STRING_TYPES",
    "is_container",
    "native_stub_type",
    "python_type",
    "stub_annotation",
]
