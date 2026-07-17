"""Action client — ROS 2 action-style communication over Zenoh.

Provides an interface to interact with ROS 2 action servers.
Supports sending goals, receiving feedback, and retrieving results.
Thread-safe with an internal lock.
"""

import logging
import os
import threading
from typing import Callable, Generic, Optional, cast

from .exceptions import ServiceException, ActionInvokeException
from ._proxies import ZenohSessionProxy
from ._service import ServiceClient
from ._subscriber import Subscriber
from .types import RosAction, RosService
from .types._base import (
    _SGReqT,
    _SGResT,
    _GRReqT,
    _GRResT,
    _FBMsgT,
    _GoalT,
    _ResultT,
    _FeedbackT,
)


class Action(Generic[_SGReqT, _SGResT, _GRReqT, _GRResT, _FBMsgT, _GoalT, _ResultT, _FeedbackT]):
    """ROS 2 Action client that communicates over Zenoh.

    Args:
        zenoh_session: Active Zenoh session for communication.
        action_name: Fully qualified name of the action (e.g. /fibonacci).
        action_type: The action type *class* (e.g. ``Fibonacci``) — must satisfy
            the ``RosAction`` protocol via ``ClassVar`` attributes.
        timeout: Request timeout in **milliseconds** (default: 3000).
    """

    def __init__(
            self,
            zenoh_session: ZenohSessionProxy,
            action_name: str,
            action_type: type[RosAction[_SGReqT, _SGResT, _GRReqT, _GRResT, _FBMsgT, _GoalT, _ResultT, _FeedbackT]],
            timeout: int = 3000,
    ):
        self._zenoh_session = zenoh_session
        self._action_name = action_name
        self._action_types = action_type
        self._timeout = timeout
        self._lock = threading.RLock()
        self._goal_id = self._new_goal_id()
        self._feedback_callback: Optional[
            Callable[[_FBMsgT], None]
        ] = None

        self._feedback_subscriber = Subscriber[_FBMsgT](
            zenoh_session,
            f"{self._action_name}/_action/feedback",
            self._action_types.FeedbackMessage,
        )

    def __enter__(self):
        """Enter the context manager — subscribe to feedback.

        Returns:
            Action: The Action instance.
        """
        self._feedback_subscriber.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit the context manager — unsubscribe from feedback."""
        self._feedback_subscriber.unsubscribe()

    @property
    def feedback_callback(self) -> Optional[Callable[[_FBMsgT], None]]:
        """Return the current feedback callback.

        Returns:
            The callback function, if set, or None.
        """
        return self._feedback_callback

    @feedback_callback.setter
    def feedback_callback(
        self, callback_func: Callable[[_FBMsgT], None]
    ):
        """Set the feedback callback function.

        Args:
            callback_func: Function to call when feedback is received.
        """
        self._feedback_callback = callback_func

    def send_goal(self, goal: _GoalT | None = None) -> _SGResT:
        """Send a goal to the action server.

        Wraps the goal dataclass into a ``SendGoal_Request`` with a
        managed ``goal_id``, and subscribes to feedback if a callback
        is set.

        Args:
            goal: The action goal dataclass (e.g. ``Fibonacci_Goal``).
                If ``None``, a default-constructed goal is used.

        Returns:
            Response from the send_goal service as a typed dataclass.

        Raises:
            ActionInvokeException: If the service call fails or times out.
        """
        with self._lock:
            if (callback := self._feedback_callback) is not None:
                self._feedback_subscriber.subscribe(callback)
            else:
                logging.warning(
                    "Feedback callback not provided for %s",
                    self._action_name,
                )

            # Construct SendGoal_Request with managed goal_id + user goal.
            if goal is None:
                goal = self._action_types.Goal()
            payload = self._action_types.SendGoal_Request()
            setattr(payload, "goal", goal)
            setattr(payload, "goal_id", tuple(self._goal_id))

            # Build an ad-hoc service class for the internal send_goal call.
            _send_goal_srv = type("_SendGoalSrv", (), {
                "__module__": __name__,
                "Request": self._action_types.SendGoal_Request,
                "Response": self._action_types.SendGoal_Response,
            })
            srv_client = ServiceClient[_SGReqT, _SGResT](
                self._zenoh_session,
                f"{self._action_name}/_action/send_goal",
                cast(type[RosService[_SGReqT, _SGResT]], _send_goal_srv),
            )

            try:
                return srv_client.send_request(payload, self._timeout)
            except ServiceException as e:
                raise ActionInvokeException(
                    "Failed to transmit goal to the action server"
                ) from e

    def get_result(self) -> _GRResT:
        """Retrieve the result for the current goal.

        Returns:
            Result from the get_result service as a typed dataclass.

        Raises:
            ActionInvokeException: If the service call fails or times out.
        """
        with self._lock:
            req = self._action_types.GetResult_Request()
            setattr(req, "goal_id", tuple(self._goal_id))

            _get_result_srv = type("_GetResultSrv", (), {
                "__module__": __name__,
                "Request": self._action_types.GetResult_Request,
                "Response": self._action_types.GetResult_Response,
            })
            srv_client = ServiceClient[_GRReqT, _GRResT](
                self._zenoh_session,
                f"{self._action_name}/_action/get_result",
                cast(type[RosService[_GRReqT, _GRResT]], _get_result_srv),
            )

            try:
                return srv_client.send_request(req, self._timeout)
            except ServiceException as e:
                raise ActionInvokeException(
                    "Failed to receive result from the action server"
                ) from e

    # ── Internal helpers ─────────────────────────────────────────────

    @staticmethod
    def _new_goal_id() -> list[int]:
        """Generate a new random goal ID.

        Uses cryptographically random bytes so the full 256^16 keyspace
        is available, matching ROS 2's UUID goal_id semantics.

        Returns:
            list[int]: 16 random bytes (0-255).
        """
        return list(os.urandom(16))
