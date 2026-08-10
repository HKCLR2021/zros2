"""ZRosClient — unified entry point for Zenoh-based ROS 2 communication.

Provides factory methods for creating ROS-like communication primitives:
publishers, subscribers, service clients, and action clients.
All factory methods require an explicit ``namespace`` argument.
Pass ``namespace=""`` to use unnamespaced topics.
"""

import os
import time
import types

import zenoh

from ._session import ZenohSessionProxy
from .discovery._liveliness import Liveliness, LivelinessType
from .discovery._qos import Qos
from .endpoints._action import Action
from .endpoints._publisher import Publisher
from .endpoints._service import ServiceClient
from .endpoints._subscriber import Subscriber
from .types._base import RosMessage
from .types._protocols import RosAction, RosService

_SERVICE_POLL_INTERVAL = 0.1  # seconds between availability polls


class ZRosClient:
    """ROS-like client using Zenoh as the communication middleware.

    Accepts either a path to a Zenoh configuration file or a
    :class:`zenoh.Config` object directly.

    Args:
        config: Either a path (``str``) to a Zenoh configuration file
            (JSON5) or a pre-built :class:`zenoh.Config` object.

    Raises:
        FileNotFoundError: If ``config`` is a ``str`` but the file does
            not exist.
        TypeError: If ``config`` is neither a ``str`` nor a
            :class:`zenoh.Config`.
        zenoh.ZError: If Zenoh session cannot be opened.
    """

    def __init__(
        self,
        config: str | zenoh.Config,
    ):
        if type(config) is str:
            if not os.path.exists(config):
                raise FileNotFoundError("Zenoh Config file not found")
            zenoh_config = zenoh.Config.from_file(config)
        elif type(config) is zenoh.Config:
            zenoh_config = config
        else:
            raise TypeError(
                f"Expected str or zenoh.Config, got {type(config).__name__}"
            )

        self._zenoh_session: zenoh.Session = zenoh.open(zenoh_config)
        self._session_proxy: ZenohSessionProxy = ZenohSessionProxy(self._zenoh_session)

    def __enter__(self):
        """Enter the context manager.

        Returns:
            ZRosClient: The client instance.
        """
        self._zenoh_session.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        """Exit the context manager and close the Zenoh session."""
        self.close()

    def close(self) -> None:
        """Close the underlying Zenoh session.

        Idempotent — safe to call multiple times; the context manager
        calls it on exit.
        """
        if not self._zenoh_session.is_closed():
            self._zenoh_session.close()

    @property
    def session(self) -> ZenohSessionProxy:
        """Return the Zenoh session proxy.

        Returns:
            ZenohSessionProxy: Wrapped Zenoh session.
        """
        return self._session_proxy

    # ── Publisher ────────────────────────────────────────────────────

    def create_publisher[MsgT: RosMessage](
        self,
        topic: str,
        message_type: type[MsgT],
        *,
        namespace: str = "",
    ) -> Publisher[MsgT]:
        """Create a publisher for publish-subscribe communication.

        Args:
            topic: Topic name to publish to (without prefix).
            message_type: ROS message class (e.g. ``std_msgs.msg.String``).
            namespace: Device namespace.  Empty string means no namespace.

        Returns:
            Publisher: Configured publisher instance.
        """
        full = f"{namespace}/{topic.lstrip('/')}" if namespace else topic
        return Publisher(self._session_proxy, full, message_type)

    # ── Subscriber ───────────────────────────────────────────────────

    def create_subscriber[MsgT: RosMessage](
        self,
        topic: str,
        message_type: type[MsgT],
        *,
        namespace: str = "",
    ) -> Subscriber[MsgT]:
        """Create a subscriber for publish-subscribe communication.

        Args:
            topic: Topic name to subscribe to (without prefix).
            message_type: ROS message class.
            namespace: Device namespace.  Empty string means no namespace.

        Returns:
            Subscriber: Configured subscriber instance.
        """
        full = f"{namespace}/{topic.lstrip('/')}" if namespace else topic
        return Subscriber(self._session_proxy, full, message_type)

    # ── Service Client ───────────────────────────────────────────────

    def create_service_client[ReqT: RosMessage, ResT: RosMessage](
        self,
        service_name: str,
        service_type: type[RosService[ReqT, ResT]],
        *,
        namespace: str = "",
    ) -> ServiceClient[ReqT, ResT]:
        """Create a service client for request-response communication.

        Args:
            service_name: Name of the service (without prefix).
            service_type: The service type *class* (e.g. ``QueryTrajectory``) —
                must satisfy the ``RosService`` protocol via ``ClassVar``
                attributes (``.Request`` and ``.Response``).
            namespace: Device namespace.  Empty string means no namespace.

        Returns:
            ServiceClient: Configured service client instance.
        """
        full = f"{namespace}/{service_name.lstrip('/')}" if namespace else service_name
        return ServiceClient(self._session_proxy, full, service_type)

    # ── Service readiness ───────────────────────────────────────────────

    def service_is_ready(
        self,
        service_name: str,
        ros2_type: str,
        *,
        namespace: str = "",
    ) -> bool:
        """Return whether a service server is currently alive.

        Detection uses the liveliness token that servers declare for
        ``LivelinessType.SERVICE_SERVER`` — the match is exact on both
        name and type, so a server of a different type never counts as
        ready.  Pass the type string explicitly, e.g.
        ``MyService.__ros_name__`` (``"my_pkg/srv/MyService"``).  Service
        liveliness keys carry no QoS, so no ``qos`` parameter exists.

        Args:
            service_name: Name of the service (without prefix).
            ros2_type: ROS 2 type string of the expected service
                (e.g. ``"my_pkg/srv/MyService"``).
            namespace: Device namespace.  Empty string means no namespace.

        Returns:
            True if a server with this exact name and type is alive.
        """
        liveliness = self.create_liveliness(
            LivelinessType.SERVICE_SERVER,
            name=service_name,
            ros2_type=ros2_type,
            namespace=namespace,
        )
        return bool(liveliness.get())

    def wait_for_service(
        self,
        service_name: str,
        ros2_type: str,
        timeout_ms: int | None = None,
        *,
        namespace: str = "",
    ) -> bool:
        """Block until a service server with the given type is available.

        The match is exact on both name and type (no wildcards).  Pass
        the type string explicitly, e.g. ``MyService.__ros_name__``.

        Args:
            service_name: Name of the service (without prefix).
            ros2_type: ROS 2 type string of the expected service
                (e.g. ``"my_pkg/srv/MyService"``).
            timeout_ms: Timeout in **milliseconds**.  ``None`` waits
                indefinitely (default).
            namespace: Device namespace.  Empty string means no namespace.

        Returns:
            True if a matching server appeared within the timeout, False
            otherwise.
        """
        liveliness = self.create_liveliness(
            LivelinessType.SERVICE_SERVER,
            name=service_name,
            ros2_type=ros2_type,
            namespace=namespace,
        )
        if timeout_ms is None:
            while not liveliness.get():
                time.sleep(_SERVICE_POLL_INTERVAL)
            return True
        deadline = time.monotonic() + timeout_ms / 1000.0
        while time.monotonic() < deadline:
            if liveliness.get():
                return True
            time.sleep(_SERVICE_POLL_INTERVAL)
        return bool(liveliness.get())

    # ── Action Client ────────────────────────────────────────────────

    def create_action_client[
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
        timeout: int | None = None,
        *,
        namespace: str = "",
    ) -> Action[SGReqT, SGResT, GRReqT, GRResT, FBMsgT, GoalT, ResultT, FeedbackT]:
        """Create an action client for long-running tasks.

        Args:
            action_name: Name of the action (without prefix).
            action_type: The action type *class* (e.g. ``Fibonacci``) —
                must satisfy the ``RosAction`` protocol via ``ClassVar``
                attributes.
            timeout: Optional timeout in **milliseconds** (default: 3000).
            namespace: Device namespace.  Empty string means no namespace.

        Returns:
            Action: Configured action client instance.
        """
        if timeout is None:
            timeout = 3000
        full = f"{namespace}/{action_name.lstrip('/')}" if namespace else action_name
        return Action(self._session_proxy, full, action_type, timeout)

    # ── Liveliness ───────────────────────────────────────────────────

    def create_liveliness(
        self,
        entity: LivelinessType,
        name: str = "*",
        ros2_type: str = "*",
        qos: Qos | str | None = None,
        *,
        namespace: str = "",
    ) -> Liveliness:
        """Create a Liveliness helper for entity discovery.

        Args:
            entity: Entity type (a :class:`LivelinessType` member).
            name: Topic / service / action name (default ``"*"``).
            ros2_type: ROS type string (default ``"*"``).
            qos: QoS constraint (a :class:`Qos` instance or wildcard).
                Defaults to :meth:`Qos.any`.
            namespace: Device namespace.  Empty string means no namespace.

        Returns:
            Liveliness: Configured liveliness helper.
        """
        if qos is None:
            qos = Qos.any()
        full = f"{namespace}/{name.lstrip('/')}" if namespace else name
        return Liveliness(
            self._session_proxy,
            entity,
            full,
            ros2_type,
            qos,
        )
