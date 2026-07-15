"""Type system for zros2.

Provides protocols for structural type-checking, concrete type
containers, and serialization helpers for ROS 2 message types.

Usage::

    from zros2.types import RosMessage, ServiceTypes, ActionTypes
    from zros2.types.utils import from_attributes, from_dict, to_dict
"""

from . import utils
from ._base import (
    RosMessage,
    _ReqT as ReqT,
    _ResT as ResT,
    _MsgT as MsgT,
    _SGReqT as SGReqT,
    _SGResT as SGResT,
    _GRReqT as GRReqT,
    _GRResT as GRResT,
    _FBMsgT as FBMsgT,
    _GoalT as GoalT,
    _ResultT as ResultT,
    _FeedbackT as FeedbackT,
)
from .protocols import RosService, RosAction
from .containers import ServiceTypes, ActionTypes

__all__ = [
    "utils",
    "RosMessage",
    "RosService",
    "RosAction",
    "ServiceTypes",
    "ActionTypes",
    "ReqT",
    "ResT",
    "MsgT",
    "SGReqT",
    "SGResT",
    "GRReqT",
    "GRResT",
    "FBMsgT",
    "GoalT",
    "ResultT",
    "FeedbackT",
]
