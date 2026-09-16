"""Zenoh key mapping for ROS 2 action channels.

``zenoh-plugin-ros2dds`` exposes each action as five keys under
``{action_name}/_action/``.  This module is the runtime counterpart of
the generator's IDL expansion (``zros2.generator.semantics._action``):
the generator owns type layout, this module owns transport paths.
"""

from enum import StrEnum


class ActionChannel(StrEnum):
    """The five Zenoh channels that make up one ROS 2 action."""

    SEND_GOAL = "send_goal"
    GET_RESULT = "get_result"
    CANCEL_GOAL = "cancel_goal"
    FEEDBACK = "feedback"
    STATUS = "status"


def action_key(action_name: str, channel: ActionChannel) -> str:
    """Return the Zenoh key expression for an action channel.

    Args:
        action_name: Fully qualified action name (namespace already applied).
        channel: One of the five action channels.

    Returns:
        Key expression ``{action_name}/_action/{channel}``.
    """
    return f"{action_name}/_action/{channel}"


__all__ = [
    "ActionChannel",
    "action_key",
]
