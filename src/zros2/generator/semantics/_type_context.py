"""Type resolution context: package, root package, constants, and bounds."""

from collections.abc import Mapping
from dataclasses import dataclass

from zros2.generator.parsing._models import MsgDefinition
from zros2.generator.parsing._types import parse_type

from ._bounds import resolve_bound
from ._literal_values import parse_literal
from ._native_types import INT_TYPES
from ._resolve_types import ResolvedType, resolve_type


def constant_int_map(defn: MsgDefinition) -> dict[str, int]:
    """Collect integer constants so they can be substituted into bounds."""
    result: dict[str, int] = {}
    for const in defn.constants:
        info = parse_type(const.type_str)
        if const.default is None:
            raise ValueError(f"{defn.full_name}.{const.name}: missing constant value")
        if info.base_name in INT_TYPES:
            value = parse_literal(
                const.default, info, f"{defn.full_name}.{const.name}"
            )
            if not isinstance(value, int):
                raise ValueError(
                    f"{defn.full_name}.{const.name}: expected an integer"
                )
            result[const.name] = value
    return result


def resolve_size(
    value: int | str | None,
    constants: Mapping[str, int],
    context: str,
) -> int:
    """Compatibility alias for :func:`._bounds.resolve_bound`."""
    return resolve_bound(value, constants, context)


@dataclass(frozen=True)
class TypeContext:
    """Resolve types and bounds for one interface definition."""

    package: str
    root_package: str
    constants: Mapping[str, int]

    def resolve(self, type_str: str) -> ResolvedType:
        """Resolve *type_str* with this context's constants."""
        return resolve_type(
            type_str,
            self.package,
            self.root_package,
            constants=self.constants,
        )

    def bound(self, value: int | str | None, context: str) -> int:
        """Resolve a bound with this context's constants."""
        return resolve_size(value, self.constants, context)


def build_type_context(
    defn: MsgDefinition,
    root_package: str = "",
) -> TypeContext:
    """Build a :class:`TypeContext` for *defn*."""
    return TypeContext(
        package=defn.package,
        root_package=root_package,
        constants=constant_int_map(defn),
    )


__all__ = [
    "TypeContext",
    "build_type_context",
    "constant_int_map",
    "resolve_size",
]
