"""Publisher endpoint for sending ROS messages over Zenoh."""

import types
from contextlib import suppress

import zenoh

from .._session import ZenohSessionProxy
from ..types._base import RosMessage


class Publisher[MsgT: RosMessage]:
    """Context manager for publishing ROS messages over Zenoh.

    Args:
        zenoh_session: Zenoh session for publishing.
        topic: Zenoh topic key expression.
        message_type: ROS message class (e.g. ``std_msgs.msg.String``).
    """

    def __init__(
        self,
        zenoh_session: ZenohSessionProxy,
        topic: str,
        message_type: type[MsgT],
    ) -> None:
        self._topic = topic
        self._message_type = message_type
        self._zenoh_session = zenoh_session
        self._publisher: zenoh.Publisher | None = self._zenoh_session.declare_publisher(
            topic
        )

    def __enter__(self) -> "Publisher[MsgT]":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        self.destroy()

    def publish(self, data: MsgT) -> None:
        """Publish a ROS message.

        Args:
            data: Typed message instance (dataclass) to publish.

        Raises:
            RuntimeError: If the publisher has already been destroyed.
        """
        if self._publisher is None:
            raise RuntimeError(f"Publisher for '{self._topic}' has been destroyed")
        self._publisher.put(data.serialize())

    def destroy(self) -> None:
        """Undeclare the publisher.

        Idempotent — safe to call multiple times.
        """
        if self._publisher is not None:
            with suppress(Exception):
                self._publisher.undeclare()
            self._publisher = None


__all__ = ["Publisher"]
