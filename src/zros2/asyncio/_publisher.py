"""Async publisher bridge for zros2.

The core :mod:`zros2` package is synchronous: :class:`zros2.Publisher`
declares the publisher at construction and hands the CDR payload to
Zenoh on ``publish``.  This module wraps that endpoint so ``publish``
and ``aclose`` run on worker threads and never block the event loop,
mirroring the sync factory surface via
:meth:`AsyncRobotClient.create_publisher`.
"""

import asyncio
from typing import Self

from .._session import ZenohSessionProxy
from ..endpoints._publisher import Publisher
from ..types._base import RosMessage


class AsyncPublisher[MsgT: RosMessage]:
    """Async wrapper around the sync :class:`zros2.Publisher`.

    Args:
        zenoh_session: Active Zenoh session.
        topic: Zenoh topic key expression.
        message_type: ROS message class (e.g. ``std_msgs.msg.String``).
    """

    def __init__(
        self,
        zenoh_session: ZenohSessionProxy,
        topic: str,
        message_type: type[MsgT],
    ) -> None:
        self._publisher = Publisher(zenoh_session, topic, message_type)

    async def publish(self, data: MsgT) -> None:
        """Publish a ROS message without blocking the event loop.

        Args:
            data: Typed message instance (dataclass) to publish.

        Raises:
            RuntimeError: If the publisher has already been closed.
        """
        await asyncio.to_thread(self._publisher.publish, data)

    async def aclose(self) -> None:
        """Undeclare the publisher.

        Idempotent — safe to call multiple times.
        """
        await asyncio.to_thread(self._publisher.destroy)

    async def __aenter__(self) -> Self:
        """Enter the async context manager."""
        return self

    async def __aexit__(self, *args: object) -> None:
        """Exit the async context manager and undeclare the publisher."""
        await self.aclose()


__all__ = ["AsyncPublisher"]
