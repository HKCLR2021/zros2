"""Generic dataclass utility functions for ROS message types."""

from collections.abc import Sequence as AbcSequence
from dataclasses import fields, is_dataclass
from typing import Annotated, Any, TypeVar, Union, cast, get_args, get_origin, get_type_hints

from ._base import RosMessage

T = TypeVar("T", bound=RosMessage)


def from_dict(cls: type[T], data: dict[str, Any]) -> T:
    """Convert a dictionary to a ROS message type instance.

    Recursively converts nested dataclasses, sequences (list[T]), and primitive
    types.  Does NOT support numpy ndarray fields (use ``_collections.dict_to_msg``
    for that).

    Args:
        cls: A ROS message type (a dataclass that implements ``RosMessage``).
        data: Dictionary with field values.

    Returns:
        An instance of ``cls``.

    Raises:
        KeyError: If a required field is missing from ``data``.
        TypeError: If a field value has the wrong type.
        RecursionError: If a circular reference is detected in the data.
    """
    return _from_dict_impl(cls, data)


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
    kwargs: dict[str, Any] = {}
    hints = get_type_hints(cls)
    for f in fields(cls):
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
                    kwargs[f.name] = from_attributes(inner, value)
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


def to_dict(obj: T, *, max_depth: int = 64) -> dict[str, Any]:  # type: ignore[reportInvalidTypeVarUse]
    """Convert a ROS message instance to a plain dictionary.

    Recursively converts nested ROS message types (dataclasses), lists,
    tuples, dicts, bytes, and primitives.  NumPy arrays are converted to
    lists (if NumPy is available).

    Args:
        obj: A ROS message instance to convert.
        max_depth: Maximum recursion depth.

    Returns:
        A JSON-compatible dictionary.

    Raises:
        TypeError: If ``obj`` is not a ROS message type.
        RecursionError: If ``max_depth`` is exceeded.
    """
    if not isinstance(obj, RosMessage):
        raise TypeError(f"Expected a ROS message instance, got {type(obj).__name__}")
    return _to_dict_value(obj, max_depth=max_depth)


# ── Internal helpers ──────────────────────────────────────────────────────────


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
        # Subscripted generics (e.g. list[int]) can't be used with isinstance.
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


def _to_dict_value(obj: Any, *, max_depth: int = 64, _depth: int = 0) -> Any:
    """Recursive helper that converts any nested value to plain Python objects."""
    if _depth > max_depth:
        raise RecursionError(f"Maximum recursion depth ({max_depth}) exceeded")

    # Dataclass → dict
    if is_dataclass(obj):
        result: dict[str, Any] = {}
        for field in fields(obj):
            value = getattr(obj, field.name)
            result[field.name] = _to_dict_value(
                value, max_depth=max_depth, _depth=_depth + 1
            )
        return result

    # List / tuple → list
    if isinstance(obj, (list, tuple)):
        return [
            _to_dict_value(item, max_depth=max_depth, _depth=_depth + 1) for item in obj
        ]

    # Dict → dict
    if isinstance(obj, dict):
        return {
            k: _to_dict_value(v, max_depth=max_depth, _depth=_depth + 1)
            for k, v in obj.items()
        }

    # Bytes → hex string
    if isinstance(obj, bytes):
        return obj.hex()

    # NumPy arrays (optional dependency)
    try:
        import numpy as np

        if isinstance(obj, np.ndarray):
            return obj.tolist()
    except ImportError:
        pass

    # Primitives (int, float, str, bool, None)
    return obj


def _from_dict_impl(
    cls: type[T], data: dict[str, Any], *, _seen: set[int] | None = None
) -> T:
    """Internal version of ``from_dict`` with cycle-detection support."""
    if not issubclass(cls, RosMessage):
        raise TypeError(f"Expected a ROS message type, got {cls}")
    assert is_dataclass(cls), f"{cls} must be a dataclass"

    if _seen is None:
        _seen = set()
    data_id = id(data)
    if data_id in _seen:
        raise RecursionError(
            f"Circular reference detected when processing {cls.__name__}")
    _seen.add(data_id)

    try:
        hints = get_type_hints(cls)
        kwargs: dict[str, Any] = {}

        for field in fields(cls):
            if field.name not in data:
                raise KeyError(
                    f"Missing required field '{field.name}' for {cls.__name__}")

            value = data[field.name]
            field_type = hints.get(field.name)

            if field_type is None:
                kwargs[field.name] = value
                continue

            if value is None:
                kwargs[field.name] = None
                continue

            # Peel pycdr2 Annotated wrappers (e.g. sequence[uint8] → Sequence[...])
            # then unwrap Optional[T] → T
            inner_type = _unannotate(field_type)
            inner_type = _unwrap_optional(inner_type)
            inner_type = _unannotate(inner_type)
            origin = get_origin(inner_type)

            if (isinstance(inner_type, type)
                    and is_dataclass(inner_type)
                    and isinstance(value, dict)):
                kwargs[field.name] = _from_dict_impl(
                    cast(type[RosMessage], inner_type), value, _seen=_seen)
            elif origin is list or origin is tuple or origin is AbcSequence:
                if isinstance(value, bytes):
                    value = list(value)
                if not isinstance(value, (list, tuple)):
                    raise TypeError(
                        f"Expected list/tuple for field '{field.name}', "
                        f"got {type(value).__name__}")
                args = get_args(inner_type)
                item_type = args[0] if args else Any
                target_type = list if origin is AbcSequence else (list if origin is list else tuple)
                if isinstance(item_type, type) and is_dataclass(item_type):
                    converted: list[Any] = []
                    for item in value:
                        if isinstance(item, dict):
                            converted.append(_from_dict_impl(
                                cast(type[RosMessage], item_type),
                                item, _seen=_seen))
                        elif isinstance(item, item_type):
                            converted.append(item)
                        else:
                            raise TypeError(
                                f"Expected dict or {_type_name(item_type)} for items "
                                f"of field '{field.name}', got {type(item).__name__}")
                    kwargs[field.name] = target_type(converted)
                else:
                    kwargs[field.name] = target_type(value)
            else:
                if not _check_type(value, inner_type):
                    raise TypeError(
                        f"Expected type {_type_name(inner_type)} "
                        f"for field '{field.name}', got {type(value).__name__}")
                kwargs[field.name] = value

        return cast(T, cls(**kwargs))
    finally:
        _seen.discard(data_id)
