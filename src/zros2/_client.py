"""ZRosClient — unified entry point for Zenoh-based ROS 2 communication.

Provides factory methods for creating ROS-like communication primitives:
publishers, subscribers, service clients, and action clients.
All factory methods require an explicit ``namespace`` argument.
Pass ``namespace=""`` to use unnamespaced topics.
"""

import os

import zenoh

from ._action import Action
from ._liveliness import Liveliness, LivelinessType, Qos
from ._proxies import ZenohSessionProxy
from ._publisher import Publisher
from ._service import ServiceClient
from ._subscriber import Subscriber
from .types import RosAction, RosService
from .types._base import (
    _ReqT,
    _ResT,
    _MsgT,
    _SGReqT,
    _SGResT,
    _GRReqT,
    _GRResT,
    _FBMsgT,
    _GoalT,
    _ResultT,
    _FeedbackT,
)


class ZRosClient:
    """ROS-like client using Zenoh as the communication middleware.

    Args:
        config_path: Path to a Zenoh configuration file (JSON5).

    Raises:
        FileNotFoundError: If the configuration file does not exist.
        zenoh.ZError: If Zenoh session cannot be opened.
    """

    def __init__(self, config_path: str):
        if not os.path.exists(config_path):
            raise FileNotFoundError('Zenoh Config file not found')

        zenoh_config = zenoh.Config.from_file(config_path)
        self._zenoh_session: zenoh.Session = zenoh.open(zenoh_config)
        self._session_proxy: ZenohSessionProxy = ZenohSessionProxy(self._zenoh_session)

    def __enter__(self):
        """Enter the context manager.

        Returns:
            ZRosClient: The client instance.
        """
        self._zenoh_session.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit the context manager and clean up Zenoh resources."""
        self._zenoh_session.__exit__(exc_type, exc_val, exc_tb)

    @property
    def session(self) -> ZenohSessionProxy:
        """Return the Zenoh session proxy.

        Returns:
            ZenohSessionProxy: Wrapped Zenoh session.
        """
        return self._session_proxy

    # ── Publisher ────────────────────────────────────────────────────

    def create_publisher(
        self,
        topic: str,
        message_type: type[_MsgT],
        *,
        namespace: str = "",
    ) -> Publisher[_MsgT]:
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

    def create_subscriber(
        self,
        topic: str,
        message_type: type[_MsgT],
        *,
        namespace: str = "",
    ) -> Subscriber[_MsgT]:
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

    def create_srv_client(
        self,
        service_name: str,
        service_type: type[RosService[_ReqT, _ResT]],
        *,
        namespace: str = "",
    ) -> ServiceClient[_ReqT, _ResT]:
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

    # ── Action Client ────────────────────────────────────────────────

    def create_action_client(
        self,
        action_name: str,
        action_type: type[RosAction[_SGReqT, _SGResT, _GRReqT, _GRResT, _FBMsgT, _GoalT, _ResultT, _FeedbackT]],
        timeout: int | None = None,
        *,
        namespace: str = "",
    ) -> Action[_SGReqT, _SGResT, _GRReqT, _GRResT, _FBMsgT, _GoalT, _ResultT, _FeedbackT]:
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
        timeout = timeout or 3000
        full = f"{namespace}/{action_name.lstrip('/')}" if namespace else action_name
        return Action(self._session_proxy, full, action_type, timeout)

    # ── Liveliness ───────────────────────────────────────────────────

    def create_liveliness(
        self,
        entity: LivelinessType,
        name: str = "*",
        ros2_type: str = "*",
        qos: Qos | str = Qos.any(),
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
        full = f"{namespace}/{name.lstrip('/')}" if namespace else name
        return Liveliness(
            self._session_proxy,
            entity,
            full,
            ros2_type,
            qos,
        )
