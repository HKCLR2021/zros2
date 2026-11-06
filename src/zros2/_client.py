"""ZRosClient — unified entry point for Zenoh-based ROS 2 communication.

Provides factory methods for creating ROS-like communication primitives:
publishers, subscribers, service clients, and action clients.
All factory methods take an optional keyword-only ``namespace`` argument.
Pass ``namespace=""`` (the default) to use unnamespaced topics.
"""

import os
import types

import zenoh

from ._namespace import join_name
from ._session import ZenohSessionProxy
from .discovery._liveliness import Liveliness, LivelinessType
from .discovery._qos import Qos
from .discovery._readiness import (
    service_is_ready as _service_is_ready,
)
from .discovery._readiness import (
    wait_for_service as _wait_for_service,
)
from .endpoints._action import Action
from .endpoints._publisher import Publisher
from .endpoints._service import ServiceClient
from .endpoints._subscriber import Subscriber
from .types._base import RosMessage
from .types._protocols import RosAction, RosService


class ZRosClient:
    """ROS-like client using Zenoh as the communication middleware.

    Accepts either a path to a Zenoh configuration file or a
    :class:`zenoh.Config` object directly.

    Args:
        config: Either a path (``str`` / ``os.PathLike``) to a Zenoh
            configuration file (JSON5) or a pre-built :class:`zenoh.Config`
            object.

    Raises:
        FileNotFoundError: If ``config`` is a path but the file does not
            exist.
        TypeError: If ``config`` is not a path or a
            :class:`zenoh.Config`.
        zenoh.ZError: If Zenoh session cannot be opened.
    """

    def __init__(
        self,
        config: str | os.PathLike[str] | zenoh.Config,
    ):
        if isinstance(config, zenoh.Config):
            zenoh_config = config
        elif isinstance(config, (str, os.PathLike)):
            path = os.fspath(config)
            if not os.path.isfile(path):
                raise FileNotFoundError(
                    f"Zenoh config file not found: {path}"
                )
            zenoh_config = zenoh.Config.from_file(path)
        else:
            raise TypeError(
                "Expected str, os.PathLike, or zenoh.Config, "
                f"got {type(config).__name__}"
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
        return Publisher(self._session_proxy, join_name(namespace, topic), message_type)

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
        return Subscriber(
            self._session_proxy, join_name(namespace, topic), message_type
        )

    # ── Service Client ───────────────────────────────────────────────

    def create_service_client[ReqT: RosMessage, ResT: RosMessage](
        self,
        service_name: str,
        service_type: RosService[ReqT, ResT],
        *,
        namespace: str = "",
    ) -> ServiceClient[ReqT, ResT]:
        """Create a service client for request-response communication.

        Args:
            service_name: Name of the service (without prefix).
            service_type: The service type *class* (e.g. ``QueryTrajectory``) —
                must satisfy the ``RosService`` protocol via class-level
                attributes (``.Request`` and ``.Response``).
            namespace: Device namespace.  Empty string means no namespace.

        Returns:
            ServiceClient: Configured service client instance.
        """
        return ServiceClient(
            self._session_proxy, join_name(namespace, service_name), service_type
        )

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
        ``MyService.__ros_name__`` (``"my_pkg/srv/MyService"``).
        """
        return _service_is_ready(
            self._session_proxy,
            service_name,
            ros2_type,
            namespace=namespace,
        )

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
        """
        return _wait_for_service(
            self._session_proxy,
            service_name,
            ros2_type,
            timeout_ms,
            namespace=namespace,
        )

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
        timeout: int | None = None,
        *,
        namespace: str = "",
    ) -> Action[SGReqT, SGResT, GRReqT, GRResT, FBMsgT, GoalT, ResultT, FeedbackT]:
        """Create an action client for long-running tasks.

        Args:
            action_name: Name of the action (without prefix).
            action_type: The action type *class* (e.g. ``Fibonacci``) —
                must satisfy the class-object ``RosAction`` protocol.
            timeout: Optional timeout in **milliseconds** (default: 3000).
            namespace: Device namespace.  Empty string means no namespace.

        Returns:
            Action: Configured action client instance.
        """
        if timeout is None:
            timeout = 3000
        return Action(
            self._session_proxy,
            join_name(namespace, action_name),
            action_type,
            timeout,
        )

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
        return Liveliness(
            self._session_proxy,
            entity,
            join_name(namespace, name),
            ros2_type,
            qos,
        )
