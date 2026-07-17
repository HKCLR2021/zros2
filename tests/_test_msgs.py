"""Simple pycdr2-based message types for integration testing.

These types follow the same pattern as the generated code:
``@dataclass(init=False)`` + hand-written ``__init__`` + explicit
``__annotations__`` override via plain assignment (to work around pycdr2's
``IdlMeta.__prepare__`` which clears ``__annotations__`` on Python 3.12+).
"""

from dataclasses import dataclass
from typing import Any, ClassVar, Self

from pycdr2 import IdlStruct

from zros2.types.utils import from_attributes as _from_attributes
from zros2.types.utils import from_dict as _from_dict
from zros2.types.utils import to_dict as _to_dict


@dataclass(init=False)
class StringMsg(IdlStruct):
    """A simple message with a single string field (like std_msgs/String)."""

    data: str

    # Explicit __annotations__ override — pycdr2 reads this for CDR encoding.
    # Plain assignment (not annotation) to match code generator's Phase 5.
    __annotations__ = {"data": str}  # type: ignore[assignment]

    def __init__(self, *, data: str = "") -> None:
        self.data = data

    def to_dict(self) -> dict[str, Any]:
        return _to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return _from_dict(cls, data)

    @classmethod
    def from_attributes(cls, obj: Any) -> Self:
        return _from_attributes(cls, obj)


@dataclass(init=False)
class IntMsg(IdlStruct):
    """A simple message with a single int32 field."""

    data: int

    __annotations__ = {"data": int}  # type: ignore[assignment]

    def __init__(self, *, data: int = 0) -> None:
        self.data = data

    def to_dict(self) -> dict[str, Any]:
        return _to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return _from_dict(cls, data)

    @classmethod
    def from_attributes(cls, obj: Any) -> Self:
        return _from_attributes(cls, obj)


@dataclass(init=False)
class PairMsg(IdlStruct):
    """A message with two fields, useful for service request/response."""

    value: int
    label: str

    __annotations__ = {"value": int, "label": str}  # type: ignore[assignment]

    def __init__(self, *, value: int = 0, label: str = "") -> None:
        self.value = value
        self.label = label

    def to_dict(self) -> dict[str, Any]:
        return _to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return _from_dict(cls, data)

    @classmethod
    def from_attributes(cls, obj: Any) -> Self:
        return _from_attributes(cls, obj)


# ── Service Types ───────────────────────────────────────────────────


class ExampleService:
    """Minimal service type for testing request/response.

    Satisfies the ``RosService`` protocol via ``ClassVar`` attributes.
    """

    Request: ClassVar[type[IntMsg]] = IntMsg  # type: ignore[valid-type]
    Response: ClassVar[type[PairMsg]] = PairMsg  # type: ignore[valid-type]
