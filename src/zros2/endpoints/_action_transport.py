"""Transport helpers for the action client.

This module owns the three internal service calls and the two feedback/status
subscriptions.  The state machine (active goals, callbacks) stays in
``_action.py``/``_action_state.py``.
"""

from typing import cast

import zenoh

from zros2._action_msgs import CancelGoal_Request, CancelGoal_Response, GoalStatusArray
from zros2._session import ZenohSessionProxy
from zros2.exceptions import (
    ActionInvokeException,
    ActionNotAvailableException,
    ActionTimeoutException,
    ServiceException,
    ServiceNotAvailableException,
    ServiceTimeoutException,
)
from zros2.types._base import RosMessage
from zros2.types._protocols import RosAction, RosService

from ._action_keys import ActionChannel, action_key
from ._service import ServiceClient
from ._subscriber import Subscriber

_SRV_TYPE_CACHE: dict[
    tuple[str, type[RosMessage], type[RosMessage]],
    RosService[RosMessage, RosMessage],
] = {}


def _make_srv_type[ReqT: RosMessage, ResT: RosMessage](
    name: str,
    request: type[ReqT],
    response: type[ResT],
) -> RosService[ReqT, ResT]:
    """Build and cache a minimal service type exposing Request/Response."""
    key = (name, request, response)
    cached = _SRV_TYPE_CACHE.get(key)
    if cached is not None:
        return cast(RosService[ReqT, ResT], cached)
    # ``type()`` yields a dynamic class object. Cast through ``object``
    # because the checker cannot prove the dynamic class satisfies the
    # class-object protocol.
    srv_type = cast(
        RosService[ReqT, ResT],
        cast(
            object,
            type(
                name,
                (),
                {
                    "__module__": __name__,
                    "Request": request,
                    "Response": response,
                },
            ),
        ),
    )
    _SRV_TYPE_CACHE[key] = cast(RosService[RosMessage, RosMessage], srv_type)
    return srv_type


class ActionTransport[
    SGReqT: RosMessage,
    SGResT: RosMessage,
    GRReqT: RosMessage,
    GRResT: RosMessage,
    FBMsgT: RosMessage,
    GoalT: RosMessage,
    ResultT: RosMessage,
    FeedbackT: RosMessage,
]:
    """Internal service/subscriber plumbing for one action client."""

    def __init__(
        self,
        session: ZenohSessionProxy,
        action_name: str,
        action_type: RosAction[
            SGReqT,
            SGResT,
            GRReqT,
            GRResT,
            FBMsgT,
            GoalT,
            ResultT,
            FeedbackT,
        ],
        timeout: int,
    ) -> None:
        self._session = session
        self._action_name = action_name
        self._action_type = action_type
        self._timeout = timeout

    def feedback_subscriber(self) -> Subscriber[FBMsgT]:
        """Create the feedback subscriber (not yet subscribed)."""
        return Subscriber[FBMsgT](
            self._session,
            action_key(self._action_name, ActionChannel.FEEDBACK),
            self._action_type.FeedbackMessage,
        )

    def status_subscriber(self) -> Subscriber[GoalStatusArray]:
        """Create the status subscriber (not yet subscribed)."""
        return Subscriber[GoalStatusArray](
            self._session,
            action_key(self._action_name, ActionChannel.STATUS),
            GoalStatusArray,
        )

    def send_goal(self, payload: SGReqT, timeout: int) -> SGResT:
        """Invoke the internal send-goal service."""
        service_type = _make_srv_type(
            "_SendGoalSrv",
            self._action_type.SendGoal_Request,
            self._action_type.SendGoal_Response,
        )
        client = ServiceClient[SGReqT, SGResT](
            self._session,
            action_key(self._action_name, ActionChannel.SEND_GOAL),
            service_type,
        )
        try:
            return client.send_request(payload, timeout)
        except ServiceTimeoutException as error:
            raise ActionTimeoutException(
                "Timed out transmitting goal to the action server"
            ) from error
        except ServiceNotAvailableException as error:
            raise ActionNotAvailableException(
                "The action server is not available"
            ) from error
        except ServiceException as error:
            raise ActionInvokeException(
                "Failed to transmit goal to the action server"
            ) from error

    def cancel_goal(
        self,
        request: CancelGoal_Request,
        timeout: int | None,
    ) -> CancelGoal_Response:
        """Invoke the internal cancel-goal service."""
        service_type = _make_srv_type(
            "_CancelGoalSrv", CancelGoal_Request, CancelGoal_Response
        )
        client = ServiceClient[CancelGoal_Request, CancelGoal_Response](
            self._session,
            action_key(self._action_name, ActionChannel.CANCEL_GOAL),
            service_type,
        )
        try:
            return client.send_request(request, timeout)
        except ServiceTimeoutException as error:
            raise ActionTimeoutException(
                "Timed out cancelling goal on the action server"
            ) from error
        except ServiceNotAvailableException as error:
            raise ActionNotAvailableException(
                "The action server is not available"
            ) from error
        except ServiceException as error:
            raise ActionInvokeException(
                "Failed to cancel goal on the action server"
            ) from error

    def get_result(
        self,
        request: GRReqT,
        timeout: int | None,
        cancellation_token: zenoh.CancellationToken | None,
    ) -> GRResT:
        """Invoke the internal get-result service."""
        service_type = _make_srv_type(
            "_GetResultSrv",
            self._action_type.GetResult_Request,
            self._action_type.GetResult_Response,
        )
        client = ServiceClient[GRReqT, GRResT](
            self._session,
            action_key(self._action_name, ActionChannel.GET_RESULT),
            service_type,
        )
        try:
            return client.send_request(request, timeout, cancellation_token)
        except ServiceTimeoutException as error:
            raise ActionTimeoutException(
                "Timed out waiting for the action result"
            ) from error
        except ServiceNotAvailableException as error:
            raise ActionNotAvailableException(
                "The action server is not available"
            ) from error
        except ServiceException as error:
            raise ActionInvokeException(
                "Failed to receive result from the action server"
            ) from error


__all__ = ["ActionTransport"]
