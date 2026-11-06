"""State objects shared by the action client and its transport."""

from dataclasses import dataclass
from typing import Protocol

from zros2.types._base import RosMessage

_CANCEL_ALL_GOAL_ID = b"\x00" * 16


class _FeedbackMessageView[FeedbackT: RosMessage](RosMessage, Protocol):
    """Minimal view of a generated ``FeedbackMessage`` (goal_id + payload)."""

    goal_id: bytes
    feedback: FeedbackT


@dataclass(frozen=True)
class GoalHandle:
    """Handle to a sent goal, returned by :meth:`Action.send_goal`.

    Each ``send_goal`` call generates a fresh goal ID, so a single
    :class:`Action` instance can track multiple goals.  Pass the handle
    to :meth:`Action.get_result` to address a specific goal.

    Attributes:
        goal_id: 16-byte UUID of the goal, unique per ``send_goal`` call.
        accepted: Whether the action server accepted the goal.
    """

    goal_id: bytes
    accepted: bool

    def __post_init__(self) -> None:
        """Normalize the goal ID to the 16-byte wire representation."""
        goal_id = bytes(self.goal_id)
        if len(goal_id) != 16:
            raise ValueError(
                f"goal_id must be exactly 16 bytes, got {len(goal_id)}"
            )
        object.__setattr__(self, "goal_id", goal_id)


__all__ = ["GoalHandle"]
