"""Resolve ROS 2 array/string bounds against message constants."""

from collections.abc import Mapping


def resolve_bound(
    value: int | str | None,
    constants: Mapping[str, int],
    context: str,
) -> int:
    """Resolve a bound to a concrete non-negative integer."""
    if value is None:
        raise ValueError(f"{context}: missing size")
    if isinstance(value, int):
        result = value
    elif value in constants:
        result = constants[value]
    else:
        raise ValueError(f"{context}: unknown constant {value!r} used as a bound")
    if result < 0:
        raise ValueError(f"{context}: negative bound {result}")
    return result


__all__ = ["resolve_bound"]
