"""Concrete type containers for ROS 2 services and actions.

These are frozen dataclasses that hold the resolved message classes
for a service or action interface.  They are the runtime types passed
to :meth:`ZRosClient.create_service_client` and
:meth:`ZRosClient.create_action_client`.
"""

import dataclasses

from ._base import RosMessage


@dataclasses.dataclass(frozen=True)
class ServiceTypes[ReqT: RosMessage, ResT: RosMessage]:
    """Stores ROS Service request/response message types.

    Attributes:
        request: The request message class.
        response: The response message class.
    """

    Request: type[ReqT]
    Response: type[ResT]


@dataclasses.dataclass(frozen=True)
class ActionTypes[
    SGReqT: RosMessage,
    SGResT: RosMessage,
    GRReqT: RosMessage,
    GRResT: RosMessage,
    FBMsgT: RosMessage,
    GoalT: RosMessage,
    ResultT: RosMessage,
    FeedbackT: RosMessage,
]:
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

    Goal: type[GoalT]
    Result: type[ResultT]
    Feedback: type[FeedbackT]
    FeedbackMessage: type[FBMsgT]
    SendGoal_Request: type[SGReqT]
    SendGoal_Response: type[SGResT]
    GetResult_Request: type[GRReqT]
    GetResult_Response: type[GRResT]


__all__ = [
    "ActionTypes",
    "ServiceTypes",
]
