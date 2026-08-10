"""Type system for zros2.

Provides protocols for structural type-checking and concrete type
containers for ROS 2 message types.

Usage::

    from zros2.types import RosMessage, ServiceTypes, ActionTypes
    from zros2.types import RosActionView
"""

from ._base import RosMessage
from ._containers import ActionTypes, ServiceTypes
from ._protocols import RosAction, RosActionView, RosService

__all__ = [
    "ActionTypes",
    "RosAction",
    "RosActionView",
    "RosMessage",
    "RosService",
    "ServiceTypes",
]
