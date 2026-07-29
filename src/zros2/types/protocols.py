"""Protocols for type-hinting ROS 2 service and action types.

Usage::

    from zros2.types.protocols import RosService, RosAction
    from zros2.types import RosMessage

    def handle(msg: RosMessage) -> None:
        data = msg.serialize()
"""

from typing import ClassVar, Protocol, runtime_checkable

from ._base import RosMessage


@runtime_checkable
class RosService[ReqT: RosMessage, ResT: RosMessage](Protocol):
    """Protocol for any generated ROS 2 service type.

    Usage in type hints::

        from zros2.types.protocols import RosService, RosMessage

        def call(svc: RosService[RosMessage, RosMessage]) -> None: ...
    """

    Request: ClassVar[type[ReqT]]  # type: ignore[valid-type]
    Response: ClassVar[type[ResT]]  # type: ignore[valid-type]


@runtime_checkable
class RosAction[
    SGReqT: RosMessage,
    SGResT: RosMessage,
    GRReqT: RosMessage,
    GRResT: RosMessage,
    FBMsgT: RosMessage,
    GoalT: RosMessage,
    ResultT: RosMessage,
    FeedbackT: RosMessage,
](Protocol):
    """Protocol for any generated ROS 2 action type.

    Usage in type hints::

        from zros2.types.protocols import RosAction, RosMessage

        def send_goal(act: RosAction[RosMessage, RosMessage,
                                     RosMessage, RosMessage,
                                     RosMessage, RosMessage,
                                     RosMessage, RosMessage]) -> None: ...
    """

    Goal: ClassVar[type[GoalT]]  # type: ignore[valid-type]
    Result: ClassVar[type[ResultT]]  # type: ignore[valid-type]
    Feedback: ClassVar[type[FeedbackT]]  # type: ignore[valid-type]
    FeedbackMessage: ClassVar[type[FBMsgT]]  # type: ignore[valid-type]
    SendGoal_Request: ClassVar[type[SGReqT]]  # type: ignore[valid-type]
    SendGoal_Response: ClassVar[type[SGResT]]  # type: ignore[valid-type]
    GetResult_Request: ClassVar[type[GRReqT]]  # type: ignore[valid-type]
    GetResult_Response: ClassVar[type[GRResT]]  # type: ignore[valid-type]


class SendGoalRequest[GoalT: RosMessage](RosMessage, Protocol):
    """Protocol for an action ``SendGoal`` request message.

    Every ROS 2 action ``SendGoal`` request has a ``goal_id`` (UUID)
    and a ``goal`` payload.
    """

    goal_id: tuple[int, ...]
    goal: GoalT


class GetResultRequest(RosMessage, Protocol):
    """Protocol for an action ``GetResult`` request message.

    Every ROS 2 action ``GetResult`` request has a ``goal_id`` (UUID).
    """

    goal_id: tuple[int, ...]


__all__ = [
    "GetResultRequest",
    "RosAction",
    "RosService",
    "SendGoalRequest",
]
