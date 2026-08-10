"""Client-bound asyncio facade for zros2.

The synchronous :mod:`zros2` core requires passing the client to every
call.  :class:`AsyncRobotClient` holds a :class:`ZRosClient` (or a bare
session proxy) once and normalizes it to the shared
:class:`ZenohSessionProxy`, so callers can invoke services and actions,
publish/subscribe, and run liveliness queries without threading the
client through every call.
"""

from collections.abc import AsyncGenerator

import zenoh

from .._client import ZRosClient
from .._session import ZenohSessionProxy
from ..discovery import LivelinessType, Qos
from ..types._base import RosMessage
from ..types._protocols import RosAction, RosService
from ._action import ActionFeedback, ActionResult, _invoke_action
from ._liveliness import _query_liveliness, _watch_liveliness
from ._publisher import AsyncPublisher
from ._service import _invoke_service
from ._subscriber import AsyncSubscriber


class AsyncRobotClient:
    """Client-bound asyncio facade for service, action, and liveliness APIs.

    Wraps the synchronous :class:`ZRosClient` (or a bare
    :class:`ZenohSessionProxy`) so blocking calls can be awaited from an
    event loop without threading the client through every call.  Blocking
    work runs on worker threads.

    Args:
        zros_client: The :class:`ZRosClient` or session proxy whose
            session is used for communication.
    """

    def __init__(self, zros_client: ZRosClient | ZenohSessionProxy) -> None:
        if isinstance(zros_client, ZRosClient):
            zros_client = zros_client.session
        self._session = zros_client

    # ── Publish / Subscribe ──────────────────────────────────────────

    def create_publisher[MsgT: RosMessage](
        self,
        topic: str,
        message_type: type[MsgT],
        *,
        namespace: str = "",
    ) -> AsyncPublisher[MsgT]:
        """Create an async publisher for publish-subscribe communication.

        Args:
            topic: Topic name to publish to (without prefix).
            message_type: ROS message class (e.g. ``std_msgs.msg.String``).
            namespace: Device namespace.  Empty string means no namespace.

        Returns:
            AsyncPublisher: Reusable publisher; ``publish`` and
                ``aclose`` run on worker threads.
        """
        full = f"{namespace}/{topic.lstrip('/')}" if namespace else topic
        return AsyncPublisher(self._session, full, message_type)

    def create_subscriber[MsgT: RosMessage](
        self,
        topic: str,
        message_type: type[MsgT],
        *,
        namespace: str = "",
    ) -> AsyncSubscriber[MsgT]:
        """Create an async subscriber for publish-subscribe communication.

        Args:
            topic: Topic name to subscribe to (without prefix).
            message_type: ROS message class.
            namespace: Device namespace.  Empty string means no namespace.

        Returns:
            AsyncSubscriber: ``async for`` iterator over received
                messages; subscribes lazily on first iteration.
        """
        full = f"{namespace}/{topic.lstrip('/')}" if namespace else topic
        return AsyncSubscriber(self._session, full, message_type)

    async def invoke_service[ReqT: RosMessage, ResT: RosMessage](
        self,
        service_name: str,
        srv_type: type[RosService[ReqT, ResT]],
        body: ReqT | None = None,
        timeout: int | None = None,
        *,
        namespace: str = "",
    ) -> ResT:
        """Invoke a service without blocking the event loop.

        Args:
            service_name: Name of the service (without prefix).
            srv_type: The service type *class* (e.g. ``QueryTrajectory``).
            body: The request payload, or ``None`` for an empty request.
            timeout: Timeout in **milliseconds** for the service call.
                ``None`` waits indefinitely (default).
            namespace: Device namespace.  Empty string means no namespace.

        Returns:
            The response payload (``Response`` sub-type).

        Raises:
            ServiceInvokeException: If the service returns an error or a
                Zenoh communication error occurs.
            ServiceNotAvailableException: If no response is received.
        """
        return await _invoke_service(
            self._session,
            service_name,
            srv_type,
            body=body,
            timeout=timeout,
            namespace=namespace,
        )

    async def invoke_action[
        SGReqT: RosMessage,
        SGResT: RosMessage,
        GRReqT: RosMessage,
        GRResT: RosMessage,
        FBMsgT: RosMessage,
        GoalT: RosMessage,
        ResultT: RosMessage,
        FeedbackT: RosMessage,
    ](
        self,
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
        single :class:`ActionResult` when the action completes.

        Args:
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
        inner = _invoke_action(
            self._session,
            action_name,
            action_type,
            goal=goal,
            timeout=timeout,
            namespace=namespace,
        )
        try:
            async for event in inner:
                yield event
        finally:
            # Closing the outer generator does not reliably close the
            # inner one through the async-for — close it explicitly so
            # the endpoint's context manager always undeclares.
            await inner.aclose()

    async def query_liveliness(
        self,
        entity: LivelinessType,
        name: str = "*",
        ros2_type: str = "*",
        qos: Qos | str | None = None,
        *,
        namespace: str = "",
    ) -> list[zenoh.Sample]:
        """Query currently alive matching entities without blocking the loop.

        Args:
            entity: Entity type (a :class:`LivelinessType` member).
            name: Topic / service / action name (default ``"*"``).
            ros2_type: ROS type string (default ``"*"``).
            qos: QoS constraint (a :class:`Qos` instance or wildcard).
                Defaults to :meth:`Qos.any`.
            namespace: Device namespace.  Empty string means no namespace.

        Returns:
            One sample per currently alive matching entity.
        """
        return await _query_liveliness(
            self._session,
            entity,
            name=name,
            ros2_type=ros2_type,
            qos=qos,
            namespace=namespace,
        )

    async def watch_liveliness(
        self,
        entity: LivelinessType,
        name: str = "*",
        ros2_type: str = "*",
        qos: Qos | str | None = None,
        *,
        namespace: str = "",
    ) -> AsyncGenerator[zenoh.Sample, None]:
        """Stream liveliness changes without blocking the event loop.

        Subscribes to matching entity liveliness tokens and yields a
        sample for every change.  Only *changes* are reported — call
        :meth:`query_liveliness` for the current snapshot.  The
        subscription is undeclared when the generator is closed or the
        consumer breaks out of the ``async for``.

        Args:
            entity: Entity type (a :class:`LivelinessType` member).
            name: Topic / service / action name (default ``"*"``).
            ros2_type: ROS type string (default ``"*"``).
            qos: QoS constraint (a :class:`Qos` instance or wildcard).
                Defaults to :meth:`Qos.any`.
            namespace: Device namespace.  Empty string means no namespace.

        Yields:
            Sample: One liveliness sample per change.
        """
        inner = _watch_liveliness(
            self._session,
            entity,
            name=name,
            ros2_type=ros2_type,
            qos=qos,
            namespace=namespace,
        )
        try:
            async for sample in inner:
                yield sample
        finally:
            # Closing the outer generator does not reliably close the
            # inner one through the async-for — close it explicitly so
            # the subscriber is always undeclared.
            await inner.aclose()


__all__ = ["AsyncRobotClient"]
