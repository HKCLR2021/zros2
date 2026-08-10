"""Simple pycdr2-based message types for integration testing.

These types follow the same pattern as the generated code:
``@dataclass(init=False)`` + hand-written ``__init__`` + explicit
``__annotations__`` override with hardcoded ``to_dict``/``from_dict``.
"""

from dataclasses import dataclass
from typing import Any, ClassVar, Self

from pycdr2 import IdlStruct

from zros2.types._utils import from_attributes as _from_attributes


@dataclass(init=False)
class StringMsg(IdlStruct):
    """A simple message with a single string field (like std_msgs/String)."""

    data: str

    __annotations__ = {"data": str}  # type: ignore

    def __init__(self, *, data: str = "") -> None:
        self.data = data

    def to_dict(self) -> dict[str, Any]:
        return {"data": self.data}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls(data=data["data"])

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
        return {"data": self.data}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls(data=data["data"])

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
        return {"value": self.value, "label": self.label}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls(value=data["value"], label=data["label"])

    @classmethod
    def from_attributes(cls, obj: Any) -> Self:
        return _from_attributes(cls, obj)


class ExampleService:
    """Minimal service type for testing request/response."""

    Request: ClassVar[type[IntMsg]] = IntMsg  # type: ignore[valid-type]
    Response: ClassVar[type[PairMsg]] = PairMsg  # type: ignore[valid-type]


class ExampleAction:
    """Minimal action type for testing create_action_client."""

    class Goal:
        """Action goal."""

        def serialize(self) -> bytes:
            return b""

        def to_dict(self) -> dict[str, Any]:
            return {}

        @classmethod
        def from_dict(cls, data: dict[str, Any]) -> "ExampleAction.Goal":
            return cls()

        @classmethod
        def from_attributes(cls, obj: Any) -> "ExampleAction.Goal":
            return cls()

    class Result:
        """Action result."""

        def serialize(self) -> bytes:
            return b""

        def to_dict(self) -> dict[str, Any]:
            return {}

        @classmethod
        def from_dict(cls, data: dict[str, Any]) -> "ExampleAction.Result":
            return cls()

        @classmethod
        def from_attributes(cls, obj: Any) -> "ExampleAction.Result":
            return cls()

    class Feedback:
        """Action feedback."""

        def serialize(self) -> bytes:
            return b""

        def to_dict(self) -> dict[str, Any]:
            return {}

        @classmethod
        def from_dict(cls, data: dict[str, Any]) -> "ExampleAction.Feedback":
            return cls()

        @classmethod
        def from_attributes(cls, obj: Any) -> "ExampleAction.Feedback":
            return cls()

    class FeedbackMessage:
        """Action feedback message."""

        @classmethod
        def deserialize(cls, data: bytes) -> "ExampleAction.FeedbackMessage":
            return cls()

        def serialize(self) -> bytes:
            return b""

        def to_dict(self) -> dict[str, Any]:
            return {}

        @classmethod
        def from_dict(cls, data: dict[str, Any]) -> "ExampleAction.FeedbackMessage":
            return cls()

        @classmethod
        def from_attributes(cls, obj: Any) -> "ExampleAction.FeedbackMessage":
            return cls()

    class SendGoal_Request:
        """Send goal request."""

        def serialize(self) -> bytes:
            return b""

        def to_dict(self) -> dict[str, Any]:
            return {}

        @classmethod
        def from_dict(cls, data: dict[str, Any]) -> "ExampleAction.SendGoal_Request":
            return cls()

        @classmethod
        def from_attributes(cls, obj: Any) -> "ExampleAction.SendGoal_Request":
            return cls()

    class SendGoal_Response:
        """Send goal response."""

        @classmethod
        def deserialize(cls, data: bytes) -> "ExampleAction.SendGoal_Response":
            return cls()

        def serialize(self) -> bytes:
            return b""

        def to_dict(self) -> dict[str, Any]:
            return {}

        @classmethod
        def from_dict(cls, data: dict[str, Any]) -> "ExampleAction.SendGoal_Response":
            return cls()

        @classmethod
        def from_attributes(cls, obj: Any) -> "ExampleAction.SendGoal_Response":
            return cls()

    class GetResult_Request:
        """Get result request."""

        def serialize(self) -> bytes:
            return b""

        def to_dict(self) -> dict[str, Any]:
            return {}

        @classmethod
        def from_dict(cls, data: dict[str, Any]) -> "ExampleAction.GetResult_Request":
            return cls()

        @classmethod
        def from_attributes(cls, obj: Any) -> "ExampleAction.GetResult_Request":
            return cls()

    class GetResult_Response:
        """Get result response."""

        @classmethod
        def deserialize(cls, data: bytes) -> "ExampleAction.GetResult_Response":
            return cls()

        def serialize(self) -> bytes:
            return b""

        def to_dict(self) -> dict[str, Any]:
            return {}

        @classmethod
        def from_dict(cls, data: dict[str, Any]) -> "ExampleAction.GetResult_Response":
            return cls()

        @classmethod
        def from_attributes(cls, obj: Any) -> "ExampleAction.GetResult_Response":
            return cls()
