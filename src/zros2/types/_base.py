"""Base protocol for ROS 2 message types.

``RosMessage`` is the structural contract every generated message class
satisfies: a ``@dataclass`` inheriting from ``pycdr2.IdlStruct`` with CDR
``serialize`` / ``deserialize`` and plain-dict conversion methods.

Generic type parameters live on each consumer (classes and functions use
PEP 695 type-parameter syntax, e.g. ``class Publisher[MsgT: RosMessage]``)
rather than shared module-level TypeVars.
"""

from typing import Protocol, Self, runtime_checkable


@runtime_checkable
class RosMessage(Protocol):
    """Protocol for any generated ROS 2 message type (structurally typed).

    A message is a ``@dataclass`` that inherits from ``pycdr2.IdlStruct``
    and can be serialized/deserialized in CDR format.
    """

    def serialize(self) -> bytes:
        """Serialize this message to CDR bytes."""
        ...

    @classmethod
    def deserialize(cls, data: bytes) -> Self:
        """Deserialize CDR bytes into a message instance."""
        ...

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> Self:
        """Create a message instance from a plain dictionary."""
        ...

    @classmethod
    def from_attributes(cls, obj: object) -> Self:
        """Create a message instance from an object with matching attributes."""
        ...

    def to_dict(self) -> dict[str, object]:
        """Convert this message to a plain dictionary."""
        ...
