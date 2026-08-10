"""Async action invocation bridge for zros2.

The core :mod:`zros2` package is synchronous: :class:`zros2.Action`
blocks on ``send_goal`` / ``get_result`` and delivers feedback on Zenoh
threads.  This module bridges that endpoint into asyncio — blocking
calls are offloaded with :func:`asyncio.to_thread` and feedback is
forwarded into the event loop through a bounded queue — so
:class:`AsyncRobotClient` can expose it as an ``async for`` stream.
"""

import asyncio
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Protocol, cast

from .._session import ZenohSessionProxy
from ..endpoints._action import Action
from ..exceptions import ActionInvokeException
from ..types._base import RosMessage
from ..types._protocols import RosAction

_FEEDBACK_QUEUE_MAX = 100


class _GetResultResponseView[ResultT: RosMessage](Protocol):
    """Minimal view of a generated ``GetResult_Response``."""

    status: int
    result: ResultT


class _FeedbackMessageView[FeedbackT: RosMessage](Protocol):
    """Minimal view of a generated ``FeedbackMessage``."""

    feedback: FeedbackT


@dataclass(frozen=True)
class ActionFeedback[FeedbackT: RosMessage]:
    """Feedback event yielded while the action is executing.

    Attributes:
        feedback: The pure feedback payload (``Feedback`` sub-type).
    """

    feedback: FeedbackT


@dataclass(frozen=True)
class ActionResult[ResultT: RosMessage]:
    """Final result event yielded when the action completes.

    Attributes:
        status: Goal status code (``action_msgs`` ``GoalStatus``).
        result: The result payload (``Result`` sub-type).
    """

    status: int
    result: ResultT


async def _invoke_action[
    SGReqT: RosMessage,
    SGResT: RosMessage,
    GRReqT: RosMessage,
    GRResT: RosMessage,
    FBMsgT: RosMessage,
    GoalT: RosMessage,
    ResultT: RosMessage,
    FeedbackT: RosMessage,
](
    session: ZenohSessionProxy,
    action_name: str,
    action_type: type[
        RosAction[
            SGReqT,
            SGResT,
            GRReqT,
            GRResT,
            FBMsgT,
            GoalT,
            ResultT,
            FeedbackT,
        ]
    ],
    goal: GoalT | None = None,
    timeout: int | None = None,
    *,
    namespace: str = "",
) -> AsyncGenerator[ActionFeedback[FeedbackT] | ActionResult[ResultT], None]:
    """Invoke an action without blocking the event loop.

    Sends ``goal`` (or a default goal when ``None``), then yields an
    :class:`ActionFeedback` for every feedback update and finally a
    single :class:`ActionResult` when the action completes.  Feedback is
    dropped when the consumer is slower than the server (bounded queue,
    oldest entries first).

    Args:
        session: The shared session proxy used for communication.
        action_name: Name of the action (without prefix).
        action_type: The action type *class* (e.g. ``Fibonacci``).
        goal: The goal payload, or ``None`` for a default goal.
        timeout: Optional timeout in **milliseconds** for the send-goal
            RPC and as a bound on the get-result wait.  ``None`` waits
            for the result indefinitely (default).
        namespace: Device namespace.  Empty string means no namespace.

    Yields:
        ActionFeedback: Every feedback update from the action server.
        ActionResult: The final goal status and result payload.

    Raises:
        ActionInvokeException: If the goal is rejected, or the
            send-goal / get-result service call fails.
    """
    loop = asyncio.get_running_loop()
    feedback_queue: asyncio.Queue[FBMsgT] = asyncio.Queue(maxsize=_FEEDBACK_QUEUE_MAX)

    def _put_nowait(message: FBMsgT) -> None:
        try:
            feedback_queue.put_nowait(message)
        except asyncio.QueueFull:
            pass

    def _forward_feedback(message: FBMsgT) -> None:
        # The QueueFull catch must run on the loop thread, where the put
        # actually executes — call_soon_threadsafe itself never raises.
        loop.call_soon_threadsafe(_put_nowait, message)

    action_timeout = 3000 if timeout is None else timeout
    full = f"{namespace}/{action_name.lstrip('/')}" if namespace else action_name
    action_client = Action(session, full, action_type, action_timeout)
    with action_client:
        action_client.feedback_callback = _forward_feedback

        goal_handle = await asyncio.to_thread(action_client.send_goal, goal)
        if not goal_handle.accepted:
            raise ActionInvokeException("Goal rejected by the action server")

        result_task = asyncio.create_task(
            asyncio.to_thread(action_client.get_result, goal_handle, timeout)
        )
        feedback_pending: asyncio.Task[FBMsgT] | None = None
        try:
            while True:
                if feedback_pending is None or feedback_pending.done():
                    feedback_pending = asyncio.create_task(feedback_queue.get())

                done, _ = await asyncio.wait(
                    (result_task, feedback_pending),
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in done:
                    if task is result_task:
                        result_response = cast(
                            _GetResultResponseView[ResultT], result_task.result()
                        )
                        yield ActionResult(
                            status=result_response.status,
                            result=result_response.result,
                        )
                        return
                    feedback_message = cast(asyncio.Task[FBMsgT], task).result()
                    yield ActionFeedback(
                        feedback=cast(
                            _FeedbackMessageView[FeedbackT], feedback_message
                        ).feedback
                    )
                    feedback_pending = None
        finally:
            if feedback_pending is not None and not feedback_pending.done():
                feedback_pending.cancel()
            if not result_task.done():
                result_task.cancel()


__all__ = ["ActionFeedback", "ActionResult", "_invoke_action"]
