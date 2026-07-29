"""Action client endpoint for ROS 2 action-style communication over Zenoh."""

import logging
import os
import threading
import types
from collections.abc import Callable
from typing import cast

from .._session import ZenohSessionProxy
from ..exceptions import ActionInvokeException, ServiceException
from ..types import RosAction, RosMessage, RosService
from ..types.protocols import GetResultRequest, SendGoalRequest
from .service import ServiceClient
from .subscriber import Subscriber

logger = logging.getLogger(__name__)


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
        timeout: Request timeout in milliseconds.
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
        self._goal_id = self._new_goal_id()
        self._feedback_callback: Callable[[FBMsgT], None] | None = None

        self._feedback_subscriber = Subscriber[FBMsgT](
            zenoh_session,
            f"{self._action_name}/_action/feedback",
            self._action_types.FeedbackMessage,
        )

    def __enter__(self):
        """Enter the context manager and subscribe to feedback."""
        self._feedback_subscriber.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        """Exit the context manager and unsubscribe from feedback."""
        self._feedback_subscriber.unsubscribe()

    @property
    def feedback_callback(self) -> Callable[[FBMsgT], None] | None:
        """Return the current feedback callback."""
        return self._feedback_callback

    @feedback_callback.setter
    def feedback_callback(self, callback_func: Callable[[FBMsgT], None]):
        """Set the feedback callback function."""
        self._feedback_callback = callback_func

    def send_goal(self, goal: GoalT | None = None) -> SGResT:
        """Send a goal to the action server.

        Args:
            goal: Action goal dataclass. A default goal is used when omitted.

        Returns:
            Response from the send-goal service.

        Raises:
            ActionInvokeException: If the service call fails or times out.
        """
        with self._lock:
            if (callback := self._feedback_callback) is not None:
                self._feedback_subscriber.subscribe(callback)
            else:
                logger.warning(
                    "Feedback callback not provided for %s",
                    self._action_name,
                )

            if goal is None:
                goal = self._action_types.Goal()
            payload = self._action_types.SendGoal_Request()
            cast(SendGoalRequest[GoalT], payload).goal = goal
            cast(SendGoalRequest[GoalT], payload).goal_id = tuple(self._goal_id)

            send_goal_service = type(
                "_SendGoalSrv",
                (),
                {
                    "__module__": __name__,
                    "Request": self._action_types.SendGoal_Request,
                    "Response": self._action_types.SendGoal_Response,
                },
            )
            service_client = ServiceClient[SGReqT, SGResT](
                self._zenoh_session,
                f"{self._action_name}/_action/send_goal",
                cast(type[RosService[SGReqT, SGResT]], send_goal_service),
            )

            try:
                return service_client.send_request(payload, self._timeout)
            except ServiceException as error:
                raise ActionInvokeException(
                    "Failed to transmit goal to the action server"
                ) from error

    def get_result(self) -> GRResT:
        """Retrieve the result for the current goal.

        Returns:
            Result from the get-result service.

        Raises:
            ActionInvokeException: If the service call fails or times out.
        """
        with self._lock:
            request = self._action_types.GetResult_Request()
            cast(GetResultRequest, request).goal_id = tuple(self._goal_id)

            get_result_service = type(
                "_GetResultSrv",
                (),
                {
                    "__module__": __name__,
                    "Request": self._action_types.GetResult_Request,
                    "Response": self._action_types.GetResult_Response,
                },
            )
            service_client = ServiceClient[GRReqT, GRResT](
                self._zenoh_session,
                f"{self._action_name}/_action/get_result",
                cast(type[RosService[GRReqT, GRResT]], get_result_service),
            )

            try:
                return service_client.send_request(request, self._timeout)
            except ServiceException as error:
                raise ActionInvokeException(
                    "Failed to receive result from the action server"
                ) from error

    @staticmethod
    def _new_goal_id() -> list[int]:
        """Generate a 16-byte random goal ID."""
        return list(os.urandom(16))


__all__ = ["Action"]
