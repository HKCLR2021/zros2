"""zros2 — lightweight ROS2-like communication over Zenoh."""

from importlib.metadata import PackageNotFoundError, version

from zenoh import Reply, Sample, SampleKind

from . import exceptions
from ._action_msgs import (
    CancelGoal_Request,
    CancelGoal_Response,
    GoalInfo,
    GoalStatus,
    GoalStatusArray,
)
from ._client import ZRosClient
from .discovery import Liveliness, LivelinessType, Qos
from .endpoints import Action, GoalHandle, Publisher, ServiceClient, Subscriber
from .types import (
    ActionTypes,
    RosAction,
    RosActionView,
    RosMessage,
    RosService,
    ServiceTypes,
)

try:
    __version__ = version("zros2")
except PackageNotFoundError:  # source tree without installed metadata
    __version__ = "0.0.0"

__all__ = [
    "Action",
    "ActionTypes",
    "CancelGoal_Request",
    "CancelGoal_Response",
    "GoalHandle",
    "GoalInfo",
    "GoalStatus",
    "GoalStatusArray",
    "Liveliness",
    "LivelinessType",
    "Publisher",
    "Qos",
    "Reply",
    "RosAction",
    "RosActionView",
    "RosMessage",
    "RosService",
    "Sample",
    "SampleKind",
    "ServiceClient",
    "ServiceTypes",
    "Subscriber",
    "ZRosClient",
    "__version__",
    "exceptions",
]
