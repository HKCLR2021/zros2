"""Action client endpoint for ROS 2 action-style communication over Zenoh."""

import logging
import os
import threading
import types
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, cast

from .._action_msgs import (
    CancelGoal_Request,
    CancelGoal_Response,
    GoalInfo,
    GoalStatusArray,
)
from .._session import ZenohSessionProxy
from ..exceptions import ActionInvokeException, ServiceException
from ..types._base import RosMessage
from ..types._protocols import GetResultRequest, RosAction, RosService, SendGoalRequest
from ._service import ServiceClient
from ._subscriber import Subscriber

logger = logging.getLogger(__name__)


_CANCEL_ALL_GOAL_ID = (0,) * 16

_SRV_TYPE_CACHE: dict[
    tuple[str, type[RosMessage], type[RosMessage]],
    type[RosService[RosMessage, RosMessage]],
] = {}


def _make_srv_type[ReqT: RosMessage, ResT: RosMessage](
    name: str,
    request: type[ReqT],
    response: type[ResT],
) -> type[RosService[ReqT, ResT]]:
    """Build a minimal service type exposing ``Request`` / ``Response``.

    ``ServiceClient`` only reads these two ClassVar members, so a
    dynamically-constructed class suffices — no generated service wrapper
    is needed for the internal ``send_goal`` / ``get_result`` transports.
    Results are cached by ``(name, request, response)`` because the three
    action transports construct one per call.
    """
    key = (name, request, response)
    cached = _SRV_TYPE_CACHE.get(key)
    if cached is not None:
        return cast(type[RosService[ReqT, ResT]], cached)
    srv_type = cast(
        type[RosService[ReqT, ResT]],
        type(
            name,
            (),
            {
                "__module__": __name__,
                "Request": request,
                "Response": response,
            },
        ),
    )
    _SRV_TYPE_CACHE[key] = cast(type[RosService[RosMessage, RosMessage]], srv_type)
    return srv_type


class _SendGoalResponseView(Protocol):
    """Minimal view of a generated ``SendGoal_Response`` (accepted flag)."""

    accepted: bool


class _FeedbackMessageView[FeedbackT: RosMessage](Protocol):
    """Minimal view of a generated ``FeedbackMessage`` (goal_id + payload)."""

    goal_id: tuple[int, ...]
    feedback: FeedbackT


@dataclass(frozen=True)
class GoalHandle:
    """Handle to a sent goal, returned by :meth:`Action.send_goal`.

    Each ``send_goal`` call generates a fresh goal ID, so a single
    :class:`Action` instance can track multiple goals.  Pass the handle
    to :meth:`Action.get_result` to address a specific goal.

    Attributes:
        goal_id: 16-byte UUID of the goal, unique per ``send_goal`` call.
        accepted: Whether the action server accepted the goal.
    """

    goal_id: tuple[int, ...]
    accepted: bool


class Action[
    SGReqT: RosMessage,
    SGResT: RosMessage,
    GRReqT: RosMessage,
    GRResT: RosMessage,
    FBMsgT: RosMessage,
    GoalT: RosMessage,
    ResultT: RosMessage,
    FeedbackT: RosMessage,
]:
    """ROS 2 action client that communicates over Zenoh.

    Args:
        zenoh_session: Active Zenoh session for communication.
        action_name: Fully qualified action name.
        action_type: Action type class satisfying the ``RosAction`` protocol.
        timeout: Request timeout in milliseconds (default: 3000).
    """

    def __init__(
        self,
        zenoh_session: ZenohSessionProxy,
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
        timeout: int = 3000,
    ):
        self._zenoh_session = zenoh_session
        self._action_name = action_name
        self._action_types = action_type
        self._timeout = timeout
        self._lock = threading.RLock()
        self._feedback_callback: Callable[[FBMsgT], None] | None = None
        self._active_goal_ids: set[bytes] = set()
        self._status_callback: Callable[[GoalStatusArray], None] | None = None
        self._feedback_subscriber = Subscriber[FBMsgT](
            zenoh_session,
            f"{self._action_name}/_action/feedback",
            self._action_types.FeedbackMessage,
        )
        self._status_subscriber = Subscriber[GoalStatusArray](
            zenoh_session,
            f"{self._action_name}/_action/status",
            GoalStatusArray,
        )

    def __enter__(self):
        """Enter the context manager.

        Subscriptions are established lazily — feedback on ``send_goal``
        (when a callback is set) and status on ``status_callback``.
        """
        self._feedback_subscriber.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        """Exit the context manager and unsubscribe from feedback/status."""
        self._feedback_subscriber.unsubscribe()
        self._status_subscriber.unsubscribe()

    @property
    def feedback_callback(self) -> Callable[[FBMsgT], None] | None:
        """Return the current feedback callback."""
        with self._lock:
            return self._feedback_callback

    @feedback_callback.setter
    def feedback_callback(self, callback_func: Callable[[FBMsgT], None]):
        """Set the feedback callback function.

        The callback receives only feedback belonging to goals sent
        through this client (filtered by ``goal_id``).
        """
        with self._lock:
            self._feedback_callback = callback_func

    @property
    def status_callback(self) -> Callable[[GoalStatusArray], None] | None:
        """Return the current status callback."""
        with self._lock:
            return self._status_callback

    @status_callback.setter
    def status_callback(self, callback_func: Callable[[GoalStatusArray], None] | None):
        """Set the status callback and subscribe to the status topic.

        The callback receives every ``GoalStatusArray`` published on
        ``{action_name}/_action/status`` (set to ``None`` to stop
        receiving).
        """
        with self._lock:
            self._status_callback = callback_func
            if callback_func is not None:
                self._ensure_status_subscription()

    def _forward_status(self, status_array: GoalStatusArray) -> None:
        """Forward a status update via the current status callback.

        The callback reference is read under the lock but invoked outside
        it, so a user callback may safely re-enter the action.
        """
        with self._lock:
            callback = self._status_callback
        if callback is not None:
            callback(status_array)

    def _ensure_status_subscription(self) -> None:
        """Subscribe the status forwarding callback once; later calls are no-ops."""
        try:
            self._status_subscriber.subscribe(self._forward_status)
        except ValueError:
            pass

    def _forward_feedback(self, message: FBMsgT) -> None:
        """Forward feedback for active goals only, via the current callback.

        The active-goal set and callback reference are read under the
        lock but the callback is invoked outside it, so a user callback
        may safely re-enter the action.
        """
        view = cast(_FeedbackMessageView[FeedbackT], message)
        with self._lock:
            if view.goal_id not in self._active_goal_ids:
                return
            callback = self._feedback_callback
        if callback is not None:
            callback(message)

    def _ensure_feedback_subscription(self) -> None:
        """Subscribe the forwarding callback once; later calls are no-ops."""
        try:
            self._feedback_subscriber.subscribe(self._forward_feedback)
        except ValueError:
            pass

    def send_goal(self, goal: GoalT | None = None) -> GoalHandle:
        """Send a goal to the action server.

        Each call generates a fresh goal ID and returns a
        :class:`GoalHandle` for that goal.  The client may be reused for
        subsequent goals.

        Args:
            goal: Action goal dataclass. A default goal is used when omitted.

        Returns:
            GoalHandle: Handle carrying the new goal ID and whether the
                server accepted the goal.

        Raises:
            ActionInvokeException: If the service call fails or times out.
        """
        with self._lock:
            if self._feedback_callback is not None:
                self._ensure_feedback_subscription()
            else:
                logger.warning(
                    "Feedback callback not provided for %s",
                    self._action_name,
                )

            if goal is None:
                goal = self._action_types.Goal()
            raw_goal_id = self._new_goal_id()
            self._active_goal_ids.add(raw_goal_id)
            goal_id = tuple(raw_goal_id)

            payload = self._action_types.SendGoal_Request()
            cast(SendGoalRequest[GoalT], payload).goal = goal
            cast(SendGoalRequest[GoalT], payload).goal_id = goal_id

            send_goal_service = _make_srv_type(
                "_SendGoalSrv",
                self._action_types.SendGoal_Request,
                self._action_types.SendGoal_Response,
            )
            service_client = ServiceClient[SGReqT, SGResT](
                self._zenoh_session,
                f"{self._action_name}/_action/send_goal",
                send_goal_service,
            )

            try:
                response = service_client.send_request(payload, self._timeout)
            except ServiceException as error:
                self._active_goal_ids.discard(raw_goal_id)
                raise ActionInvokeException(
                    "Failed to transmit goal to the action server"
                ) from error
            return GoalHandle(
                goal_id=goal_id,
                accepted=cast(_SendGoalResponseView, response).accepted,
            )

    def cancel_goal(
        self, goal_handle: GoalHandle, timeout: int | None = None
    ) -> CancelGoal_Response:
        """Request cancellation of a sent goal.

        Args:
            goal_handle: Handle returned by :meth:`send_goal` for the goal
                to cancel.
            timeout: Optional timeout in **milliseconds**.  ``None`` waits
                indefinitely (default).

        Returns:
            CancelGoal_Response: Cancel result.  ``return_code`` is one of
                the ``ERROR_*`` constants on
                :class:`~zros2.CancelGoal_Response`.

        Raises:
            ActionInvokeException: If the cancel service call fails.
        """
        return self._cancel_goal(
            CancelGoal_Request(goal_info=GoalInfo(goal_id=goal_handle.goal_id)),
            timeout,
        )

    def cancel_all_goals(self, timeout: int | None = None) -> CancelGoal_Response:
        """Request cancellation of every active goal for this action.

        Uses the ROS 2 wildcard (all-zero goal ID) accepted by action
        servers for ``cancel_all_goals``.

        Args:
            timeout: Optional timeout in **milliseconds**.  ``None`` waits
                indefinitely (default).

        Returns:
            CancelGoal_Response: Cancel result.

        Raises:
            ActionInvokeException: If the cancel service call fails.
        """
        return self._cancel_goal(
            CancelGoal_Request(goal_info=GoalInfo(goal_id=_CANCEL_ALL_GOAL_ID)),
            timeout,
        )

    def _cancel_goal(
        self, request: CancelGoal_Request, timeout: int | None
    ) -> CancelGoal_Response:
        """Transmit a cancel request to the action server."""
        with self._lock:
            cancel_service = _make_srv_type(
                "_CancelGoalSrv", CancelGoal_Request, CancelGoal_Response
            )
            service_client = ServiceClient[CancelGoal_Request, CancelGoal_Response](
                self._zenoh_session,
                f"{self._action_name}/_action/cancel_goal",
                cancel_service,
            )
            try:
                return service_client.send_request(request, timeout)
            except ServiceException as error:
                raise ActionInvokeException(
                    "Failed to cancel goal on the action server"
                ) from error

    def get_result(self, goal_handle: GoalHandle, timeout: int | None = None) -> GRResT:
        """Retrieve the result for a sent goal.

        Per ROS 2 semantics the get-result call blocks until the goal
        terminates.  Pass ``timeout`` to bound the wait; ``None`` (the
        default) waits indefinitely.

        Args:
            goal_handle: Handle returned by :meth:`send_goal` for the goal
                whose result is requested.
            timeout: Optional timeout in **milliseconds**.  ``None`` waits
                indefinitely (default).

        Returns:
            Result from the get-result service.

        Raises:
            ActionInvokeException: If the service call fails or times out.
        """
        with self._lock:
            request = self._action_types.GetResult_Request()
            cast(GetResultRequest, request).goal_id = goal_handle.goal_id

            get_result_service = _make_srv_type(
                "_GetResultSrv",
                self._action_types.GetResult_Request,
                self._action_types.GetResult_Response,
            )
            service_client = ServiceClient[GRReqT, GRResT](
                self._zenoh_session,
                f"{self._action_name}/_action/get_result",
                get_result_service,
            )

            try:
                response = service_client.send_request(request, timeout)
            except ServiceException as error:
                raise ActionInvokeException(
                    "Failed to receive result from the action server"
                ) from error
            self._active_goal_ids.discard(goal_handle.goal_id)
            return response

    @staticmethod
    def _new_goal_id() -> bytes:
        """Generate a 16-byte random goal ID."""
        return os.urandom(16)


__all__ = ["Action", "GoalHandle"]
