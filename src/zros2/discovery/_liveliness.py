"""Query and monitor ROS 2 entity liveliness over Zenoh."""

import logging
from collections.abc import Callable
from typing import Any, Self

import zenoh

from .._session import ZenohSessionProxy
from ._key import LivelinessKey, LivelinessType
from ._qos import Qos

logger = logging.getLogger(__name__)

_ENTITY_BUILDER: dict[LivelinessType, Callable[..., str]] = {
    LivelinessType.PUBLISHER: LivelinessKey.build_publisher_ke,
    LivelinessType.SUBSCRIBER: LivelinessKey.build_subscriber_ke,
    LivelinessType.SERVICE_SERVER: LivelinessKey.build_service_server_ke,
    LivelinessType.SERVICE_CLIENT: LivelinessKey.build_service_client_ke,
    LivelinessType.ACTION_SERVER: LivelinessKey.build_action_server_ke,
    LivelinessType.ACTION_CLIENT: LivelinessKey.build_action_client_ke,
}


class Liveliness:
    """Monitor and query ROS 2 entity liveliness over Zenoh."""

    def __init__(
        self,
        zenoh_session: ZenohSessionProxy,
        entity: LivelinessType,
        name: str = "*",
        ros2_type: str = "*",
        qos: Qos | str | None = None,
    ) -> None:
        builder = _ENTITY_BUILDER.get(entity)
        if builder is None:
            supported = ", ".join(item.name for item in _ENTITY_BUILDER)
            raise ValueError(
                f"Unsupported entity type {entity!r}. Use one of: {supported}"
            )

        if qos is None:
            qos = Qos.any()

        if entity in (LivelinessType.PUBLISHER, LivelinessType.SUBSCRIBER):
            self._ke = builder("*", name, ros2_type, qos=qos)
        else:
            self._ke = builder("*", name, ros2_type)
        self._zenoh_session = zenoh_session
        self._sub: zenoh.Subscriber[Any] | None = None

    def get(self) -> list[zenoh.Sample]:
        """Return currently alive matching entities."""
        return list(self._zenoh_session.liveliness().get(self._ke))

    def subscribe(
        self,
        callback: Callable[[zenoh.Sample], Any],
    ) -> zenoh.Subscriber[Any] | None:
        """Subscribe to matching entity liveliness changes.

        Args:
            callback: Handler called for each liveliness change.

        Returns:
            Active Zenoh subscriber.
        """
        self._close_subscriber()
        self._sub = self._zenoh_session.liveliness().declare_subscriber(
            self._ke, callback
        )
        return self._sub

    def close(self) -> None:
        """Undeclare the active liveliness subscriber."""
        self._close_subscriber()

    def _close_subscriber(self) -> None:
        if self._sub is not None:
            try:
                self._sub.undeclare()
            except Exception:
                logger.warning(
                    "Failed to undeclare liveliness subscriber", exc_info=True
                )
            finally:
                self._sub = None

    def __enter__(self) -> Self:
        """Enter the context manager."""
        return self

    def __exit__(self, *args: object) -> None:
        """Exit the context manager and release resources."""
        self.close()


__all__ = ["Liveliness", "LivelinessType"]
