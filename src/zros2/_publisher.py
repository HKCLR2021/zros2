"""Publisher — publishes ROS messages over Zenoh.

Wraps a Zenoh publisher to serialize typed message instances into
CDR-encoded payloads and publish them on a Zenoh topic.
"""

from typing import Generic, Optional

import zenoh

from .types._base import _MsgT
from ._proxies import ZenohSessionProxy


class Publisher(Generic[_MsgT]):
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
            message_type: type[_MsgT],
    ) -> None:
        self._topic = topic
        self._message_type = message_type
        self._zenoh_session = zenoh_session
        self._publisher: Optional[zenoh.Publisher] = (
            self._zenoh_session.declare_publisher(topic)
        )

    def __enter__(self) -> "Publisher[_MsgT]":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.destroy()

    def publish(self, data: _MsgT) -> None:
        """Publish a ROS message.

        Args:
            data: Typed message instance (dataclass) to publish.

        Raises:
            RuntimeError: If the publisher has already been destroyed.
        """
        if self._publisher is None:
            raise RuntimeError(
                f"Publisher for '{self._topic}' has been destroyed"
            )
        self._publisher.put(data.serialize())

    def destroy(self):
        """Undeclare the publisher.

        Idempotent — safe to call multiple times.
        """
        if self._publisher is not None:
            try:
                self._publisher.undeclare()
            except Exception:
                pass
            finally:
                self._publisher = None
