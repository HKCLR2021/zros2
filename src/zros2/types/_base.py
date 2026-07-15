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

_MsgT = TypeVar("_MsgT", bound=RosMessage)        # Plain ROS message (e.g. String, Twist)

# ── Service TypeVars ────────────────────────────────────────────────
# Used by RosService protocol and ServiceTypes container.

_ReqT = TypeVar("_ReqT", bound=RosMessage)         # Service Request
_ResT = TypeVar("_ResT", bound=RosMessage)         # Service Response

# ── Action TypeVars ─────────────────────────────────────────────────
# Used by RosAction protocol and ActionTypes container.
#
# NOTE: protocols.py and containers.py use slightly different names for
# some slots (e.g. _SGResT vs _ResGoalT).  Both sets are defined here;
# each module imports the names it needs.

# -- Protocol-style names --
_SGReqT = TypeVar("_SGReqT", bound=RosMessage)     # SendGoal_Request
_SGResT = TypeVar("_SGResT", bound=RosMessage)     # SendGoal_Response
_GRReqT = TypeVar("_GRReqT", bound=RosMessage)     # GetResult_Request
_GRResT = TypeVar("_GRResT", bound=RosMessage)     # GetResult_Response

# -- Container-style names --
_ResGoalT = TypeVar("_ResGoalT", bound=RosMessage) # SendGoal_Response (container alias)
_GetReqT = TypeVar("_GetReqT", bound=RosMessage)   # GetResult_Request (container alias)
_GetResT = TypeVar("_GetResT", bound=RosMessage)   # GetResult_Response (container alias)

# -- Shared (same name in both) --
_FBMsgT = TypeVar("_FBMsgT", bound=RosMessage)     # FeedbackMessage
_GoalT = TypeVar("_GoalT", bound=RosMessage)       # Goal
_ResultT = TypeVar("_ResultT", bound=RosMessage)   # Result
_FeedbackT = TypeVar("_FeedbackT", bound=RosMessage) # Feedback
