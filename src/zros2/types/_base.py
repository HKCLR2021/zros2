"""Shared TypeVars for ROS 2 message, service, and action generic types.

All generic type parameters used across the ``types`` subpackage are
defined here in one place so that ``protocols.py`` and ``containers.py``
(and any downstream code) can import them without redefinition.
"""

from typing import Any, Protocol, Self, TypeVar, runtime_checkable

# ── Base message protocol (no TypeVar dependencies) ─────────────────


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
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Create a message instance from a plain dictionary."""
        ...

    @classmethod
    def from_attributes(cls, obj: Any) -> Self:
        """Create a message instance from an object with matching attributes."""
        ...

    def to_dict(self) -> dict[str, Any]:
        """Convert this message to a plain dictionary."""
        ...


# ── Message TypeVar ─────────────────────────────────────────────────
# Used by Publisher, Subscriber, and generic message utilities.

MsgT = TypeVar("MsgT", bound=RosMessage)  # Plain ROS message (e.g. String, Twist)

# ── Service TypeVars ────────────────────────────────────────────────
# Used by RosService protocol and ServiceTypes container.

ReqT = TypeVar("ReqT", bound=RosMessage)  # Service Request
ResT = TypeVar("ResT", bound=RosMessage)  # Service Response

# ── Action TypeVars ─────────────────────────────────────────────────
# Used by RosAction protocol and ActionTypes container.
#
SGReqT = TypeVar("SGReqT", bound=RosMessage)  # SendGoal_Request
SGResT = TypeVar("SGResT", bound=RosMessage)  # SendGoal_Response
GRReqT = TypeVar("GRReqT", bound=RosMessage)  # GetResult_Request
GRResT = TypeVar("GRResT", bound=RosMessage)  # GetResult_Response

# Backward-compatible aliases for the previous container-specific names.
_ResGoalT = SGResT
_GetReqT = GRReqT
_GetResT = GRResT

FBMsgT = TypeVar("FBMsgT", bound=RosMessage)  # FeedbackMessage
GoalT = TypeVar("GoalT", bound=RosMessage)  # Goal
ResultT = TypeVar("ResultT", bound=RosMessage)  # Result
FeedbackT = TypeVar("FeedbackT", bound=RosMessage)  # Feedback
