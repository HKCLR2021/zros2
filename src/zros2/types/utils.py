"""Generic dataclass utility functions for ROS message types.

Only ``from_attributes`` remains here — it cannot be hardcoded at
generation time because it reads fields from an arbitrary source object
whose shape is unknown until runtime.

``from_dict`` and ``to_dict`` are now generated as hardcoded methods
on each message class by ``zros2.generator._codegen._msg``.
"""

from dataclasses import fields, is_dataclass
from functools import lru_cache
from typing import Annotated, Any, TypeVar, Union, cast, get_args, get_origin, get_type_hints

from ._base import RosMessage

T = TypeVar("T", bound=RosMessage)


def from_attributes(cls: type[T], obj: Any) -> T:
    """Create a ROS message instance from an object with matching attributes.

    Recursively converts nested dataclasses.  Primitive fields are read
    directly via ``getattr``.

    Args:
        cls: A ROS message type (a dataclass that implements ``RosMessage``).
        obj: Any object whose attributes match the field names of ``cls``.

    Returns:
        An instance of ``cls``.

    Raises:
        KeyError: If a required field is missing from ``obj``.
        TypeError: If a field value has an incompatible type.
    """
    assert is_dataclass(cls), f"{cls} must be a dataclass"
    kwargs: dict[str, Any] = {}
    hints = _get_cached_hints(cls)
    for f in _get_cached_fields(cls):
        if not hasattr(obj, f.name):
            raise KeyError(
                f"Missing required field '{f.name}' for {cls.__name__}")
        value = getattr(obj, f.name)
        field_type = hints.get(f.name)
        if field_type is not None:
            inner = _unannotate(field_type)
            inner = _unwrap_optional(inner)
            inner = _unannotate(inner)
            if isinstance(inner, type) and is_dataclass(inner):
                if value is None:
                    kwargs[f.name] = None
                elif isinstance(value, inner):
                    kwargs[f.name] = value
                elif not isinstance(value, (int, float, str, bool, bytes)):
                    kwargs[f.name] = from_attributes(
                        cast(type[RosMessage], inner), value)
                else:
                    raise TypeError(
                        f"Expected {_type_name(inner)} for field '{f.name}', "
                        f"got {type(value).__name__}")
            else:
                if not _check_type(value, inner):
                    raise TypeError(
                        f"Expected type {_type_name(inner)} "
                        f"for field '{f.name}', got {type(value).__name__}")
                kwargs[f.name] = value
        else:
            kwargs[f.name] = value
    return cast(T, cls(**kwargs))


# ── Internal helpers ────────────────────────────────────────


@lru_cache(maxsize=None)
def _get_cached_hints(cls: type) -> dict[str, Any]:
    """Cached wrapper around ``typing.get_type_hints``."""
    return get_type_hints(cls)


@lru_cache(maxsize=None)
def _get_cached_fields(cls_or_obj: type) -> tuple:
    """Cached wrapper around ``dataclasses.fields``."""
    return fields(cls_or_obj)


def _unwrap_optional(tp: Any) -> Any:
    """Unwrap ``Optional[T]`` / ``T | None`` to ``T``; return other types as-is."""
    origin = get_origin(tp)
    if origin is Union:
        args = [a for a in get_args(tp) if a is not type(None)]
        if len(args) == 1:
            return args[0]
    return tp


def _unannotate(tp: Any) -> Any:
    """Peel ``typing.Annotated`` wrappers (used by pycdr2) to get the real type."""
    origin = get_origin(tp)
    if origin is Annotated:
        return get_args(tp)[0]
    return tp


def _check_type(value: Any, expected: Any) -> bool:
    """Check whether a value matches an expected ROS message leaf type.

    Handles plain types (``int``, ``str``), generic aliases (``list[int]``),
    and pycdr2 types gracefully — falls back to checking the origin for
    subscripted generics that ``isinstance`` rejects.
    """
    if expected is Any:
        return True
    try:
        return isinstance(value, expected)
    except TypeError:
        origin = get_origin(expected)
        if origin is not None:
            return isinstance(value, origin)
        return True


def _type_name(tp: type) -> str:
    """Return a human-readable name for a type, handling generics."""
    origin = get_origin(tp)
    if origin is not None:
        args = get_args(tp)
        if args:
            inner = ", ".join(_type_name(a) for a in args if a is not type(None))
            return f"{origin.__name__}[{inner}]"
        return origin.__name__
    return tp.__name__
