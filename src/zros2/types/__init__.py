"""Type system for zros2.

Provides protocols for structural type-checking, concrete type
containers, and serialization helpers for ROS 2 message types.

Usage::

    from zros2.types import RosMessage, ServiceTypes, ActionTypes
    from zros2.types import from_attributes
"""

from ._base import (
    FBMsgT,
    FeedbackT,
    GoalT,
    GRReqT,
    GRResT,
    MsgT,
    ReqT,
    ResT,
    ResultT,
    RosMessage,
    SGReqT,
    SGResT,
)
from .containers import ActionTypes, ServiceTypes
from .protocols import RosAction, RosService
from .utils import from_attributes

__all__ = [
    "ActionTypes",
    "FBMsgT",
    "FeedbackT",
    "GRReqT",
    "GRResT",
    "GoalT",
    "MsgT",
    "ReqT",
    "ResT",
    "ResultT",
    "RosAction",
    "RosMessage",
    "RosService",
    "SGReqT",
    "SGResT",
    "ServiceTypes",
    "from_attributes",
]
