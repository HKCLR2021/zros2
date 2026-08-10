"""Protocols for type-hinting ROS 2 service and action types.

Usage::

    from zros2.types import RosAction, RosMessage, RosService

    def handle(msg: RosMessage) -> None:
        data = msg.serialize()
"""

from typing import ClassVar, Protocol, runtime_checkable

from ._base import RosMessage


@runtime_checkable
class RosService[ReqT: RosMessage, ResT: RosMessage](Protocol):
    """Protocol for any generated ROS 2 service type.

    Usage in type hints::

        from zros2.types import RosMessage, RosService

        def call(svc: RosService[RosMessage, RosMessage]) -> None: ...
    """

    # Checkers forbid ClassVar referencing the class's own type parameters;
    # ClassVar is required so ClassVar implementations match and class-level
    # access (type[RosService[...]].Request) stays unambiguous.
    Request: ClassVar[type[ReqT]]  # pyright: ignore[reportGeneralTypeIssues]
    Response: ClassVar[type[ResT]]  # pyright: ignore[reportGeneralTypeIssues]


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

    Goal: ClassVar[type[GoalT]]  # pyright: ignore[reportGeneralTypeIssues]
    Result: ClassVar[type[ResultT]]  # pyright: ignore[reportGeneralTypeIssues]
    Feedback: ClassVar[type[FeedbackT]]  # pyright: ignore[reportGeneralTypeIssues]
    FeedbackMessage: ClassVar[type[FBMsgT]]  # pyright: ignore[reportGeneralTypeIssues]
    SendGoal_Request: ClassVar[type[SGReqT]]  # pyright: ignore[reportGeneralTypeIssues]
    SendGoal_Response: ClassVar[type[SGResT]]  # pyright: ignore[reportGeneralTypeIssues]
    GetResult_Request: ClassVar[type[GRReqT]]  # pyright: ignore[reportGeneralTypeIssues]
    GetResult_Response: ClassVar[type[GRResT]]  # pyright: ignore[reportGeneralTypeIssues]


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
            action_type: type[RosActionView[GoalT, ResultT, FeedbackT]],
            goal: GoalT | None = None,
        ) -> None: ...
    """

    Goal: ClassVar[type[GoalT]]  # pyright: ignore[reportGeneralTypeIssues]
    Result: ClassVar[type[ResultT]]  # pyright: ignore[reportGeneralTypeIssues]
    Feedback: ClassVar[type[FeedbackT]]  # pyright: ignore[reportGeneralTypeIssues]


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
    "RosActionView",
    "RosService",
    "SendGoalRequest",
]
