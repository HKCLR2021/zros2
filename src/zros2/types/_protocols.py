"""Protocols for type-hinting ROS 2 service and action types.

Usage::

    from zros2.types import RosAction, RosMessage, RosService

    def handle(msg: RosMessage) -> None:
        data = msg.serialize()
"""

from typing import Protocol, runtime_checkable

from ._base import RosMessage


@runtime_checkable
class RosService[ReqT: RosMessage, ResT: RosMessage](Protocol):
    """Protocol for any generated ROS 2 service type.

    Usage in type hints::

        from zros2.types import RosMessage, RosService

        def call(svc: RosService[RosMessage, RosMessage]) -> None: ...
    """

    # These protocols describe the generated *class object*, not an instance.
    # A plain attribute is required: ClassVar[...] cannot reference the
    # protocol's own type parameters.
    Request: type[ReqT]
    Response: type[ResT]


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

        from zros2.types import RosAction, RosMessage

        def send_goal(act: RosAction[RosMessage, RosMessage,
                                     RosMessage, RosMessage,
                                     RosMessage, RosMessage,
                                     RosMessage, RosMessage]) -> None: ...
    """

    Goal: type[GoalT]
    Result: type[ResultT]
    Feedback: type[FeedbackT]
    FeedbackMessage: type[FBMsgT]
    SendGoal_Request: type[SGReqT]
    SendGoal_Response: type[SGResT]
    GetResult_Request: type[GRReqT]
    GetResult_Response: type[GRResT]


@runtime_checkable
class RosActionView[
    GoalT: RosMessage,
    ResultT: RosMessage,
    FeedbackT: RosMessage,
](Protocol):
    """Semantic view of an action type for consumers that only forward
    goals or observe results / feedback.

    The full :class:`RosAction` protocol carries eight message types, five
    of which are transport details (``FeedbackMessage``, ``SendGoal_*``,
    ``GetResult_*``).  Generic consumer code rarely needs those, so this
    protocol parameterizes only the three user-facing message types.

    Usage in type hints::

        from zros2.types import RosActionView, RosMessage

        async def observe_action[
            GoalT: RosMessage, ResultT: RosMessage, FeedbackT: RosMessage,
        ](
            action_type: RosActionView[GoalT, ResultT, FeedbackT],
            goal: GoalT | None = None,
        ) -> None: ...
    """

    Goal: type[GoalT]
    Result: type[ResultT]
    Feedback: type[FeedbackT]


class SendGoalRequest[GoalT: RosMessage](RosMessage, Protocol):
    """Protocol for an action ``SendGoal`` request message.

    Every ROS 2 action ``SendGoal`` request has a ``goal_id`` (UUID)
    and a ``goal`` payload.
    """

    goal_id: bytes
    goal: GoalT


class GetResultRequest(RosMessage, Protocol):
    """Protocol for an action ``GetResult`` request message.

    Every ROS 2 action ``GetResult`` request has a ``goal_id`` (UUID).
    """

    goal_id: bytes


__all__ = [
    "GetResultRequest",
    "RosAction",
    "RosActionView",
    "RosService",
    "SendGoalRequest",
]
