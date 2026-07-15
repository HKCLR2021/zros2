"""Protocols for type-hinting ROS 2 service and action types.

Usage::

    from zros2.types.protocols import RosService, RosAction
    from zros2.types import RosMessage

    def handle(msg: RosMessage) -> None:
        data = msg.serialize()
"""

from typing import ClassVar, Generic, Protocol, runtime_checkable

from ._base import (
    _ReqT,
    _ResT,
    _SGReqT,
    _SGResT,
    _GRReqT,
    _GRResT,
    _FBMsgT,
    _GoalT,
    _ResultT,
    _FeedbackT,
)


@runtime_checkable
class RosService(Protocol, Generic[_ReqT, _ResT]):
    """Protocol for any generated ROS 2 service type.

    Usage in type hints::

        from zros2.types.protocols import RosService, RosMessage

        def call(svc: RosService[RosMessage, RosMessage]) -> None: ...
    """

    Request: ClassVar[type[_ReqT]]  # type: ignore[valid-type]
    Response: ClassVar[type[_ResT]]  # type: ignore[valid-type]


@runtime_checkable
class RosAction(Protocol, Generic[_SGReqT, _SGResT, _GRReqT, _GRResT, _FBMsgT, _GoalT, _ResultT, _FeedbackT]):
    """Protocol for any generated ROS 2 action type.

    Usage in type hints::

        from zros2.types.protocols import RosAction, RosMessage

        def send_goal(act: RosAction[RosMessage, RosMessage,
                                     RosMessage, RosMessage,
                                     RosMessage, RosMessage,
                                     RosMessage, RosMessage]) -> None: ...
    """

    Goal: ClassVar[type[_GoalT]]  # type: ignore[valid-type]
    Result: ClassVar[type[_ResultT]]  # type: ignore[valid-type]
    Feedback: ClassVar[type[_FeedbackT]]  # type: ignore[valid-type]
    FeedbackMessage: ClassVar[type[_FBMsgT]]  # type: ignore[valid-type]
    SendGoal_Request: ClassVar[type[_SGReqT]]  # type: ignore[valid-type]
    SendGoal_Response: ClassVar[type[_SGResT]]  # type: ignore[valid-type]
    GetResult_Request: ClassVar[type[_GRReqT]]  # type: ignore[valid-type]
    GetResult_Response: ClassVar[type[_GRResT]]  # type: ignore[valid-type]
