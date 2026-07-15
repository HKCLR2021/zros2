"""Concrete type containers for ROS 2 services and actions.

These are frozen dataclasses that hold the resolved message classes
for a service or action interface.  They are the runtime types passed
to :meth:`ZRosClient.create_srv_client` and
:meth:`ZRosClient.create_action_client`.
"""

import dataclasses
import typing

from ._base import (
    _ReqT,
    _ResT,
    _SGReqT,
    _ResGoalT,
    _GetReqT,
    _GetResT,
    _FBMsgT,
    _GoalT,
    _ResultT,
    _FeedbackT,
)


@dataclasses.dataclass(frozen=True)
class ServiceTypes(typing.Generic[_ReqT, _ResT]):
    """Stores ROS Service request/response message types.

    Attributes:
        request: The request message class.
        response: The response message class.
    """

    Request: typing.Type[_ReqT]
    Response: typing.Type[_ResT]


@dataclasses.dataclass(frozen=True)
class ActionTypes(typing.Generic[_SGReqT, _ResGoalT, _GetReqT, _GetResT, _FBMsgT, _GoalT, _ResultT, _FeedbackT]):
    """Stores ROS Action message types.

    Attributes:
        goal: Message class for the action goal fields.
        result: Message class for the action result fields.
        feedback: Message class for the pure feedback data.
        feedback_message: Wire-format message with goal_id + feedback field.
        send_goal_request: Message class for send_goal requests.
        send_goal_response: Message class for send_goal responses.
        get_result_request: Message class for get_result requests.
        get_result_response: Message class for get_result responses.
    """

    Goal: typing.Type[_GoalT]
    Result: typing.Type[_ResultT]
    Feedback: typing.Type[_FeedbackT]
    FeedbackMessage: typing.Type[_FBMsgT]
    SendGoal_Request: typing.Type[_SGReqT]
    SendGoal_Response: typing.Type[_ResGoalT]
    GetResult_Request: typing.Type[_GetReqT]
    GetResult_Response: typing.Type[_GetResT]


__all__ = [
    "ServiceTypes",
    "ActionTypes",
]
