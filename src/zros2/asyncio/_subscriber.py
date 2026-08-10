"""Async subscriber bridge for zros2.

The core :mod:`zros2` package is synchronous: :class:`zros2.Subscriber`
delivers callbacks on Zenoh threads.  This module wraps that endpoint so
messages are forwarded into the event loop through a bounded queue and
consumed with ``async for`` — the same bridge the liveliness watcher
uses — so delivery never blocks the event loop.
"""

import asyncio
from contextlib import suppress
from typing import Self

from .._session import ZenohSessionProxy
from ..endpoints._subscriber import Subscriber
from ..types._base import RosMessage

_SUBSCRIBER_QUEUE_MAX = 100

_EOF = None  # queue sentinel: never a real message (messages are dataclasses)


class AsyncSubscriber[MsgT: RosMessage]:
    """Async iterator over messages of a Zenoh topic.

    Subscribes lazily on first iteration (or eagerly via
    :meth:`subscribe`) and forwards Zenoh-thread callbacks into the
    event loop through a bounded queue.  Messages are dropped when the
    consumer is slower than the topic (bounded queue, oldest entries
    first).  Single consumer only — concurrent ``__anext__`` calls split
    the stream between them.

    Args:
        zenoh_session: Active Zenoh session.
        topic: Zenoh topic to subscribe to.
        message_type: Expected message type with ``deserialize``.
    """

    def __init__(
        self,
        zenoh_session: ZenohSessionProxy,
        topic: str,
        message_type: type[MsgT],
    ) -> None:
        self._subscriber = Subscriber(zenoh_session, topic, message_type)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queue: asyncio.Queue[MsgT | None] | None = None
        self._subscribed = False
        self._closed = False

    async def subscribe(self) -> None:
        """Declare the subscription; idempotent.

        Raises:
            RuntimeError: If the subscriber has been closed, or the Zenoh
                session is closed.
        """
        if self._closed:
            raise RuntimeError("Subscriber has been closed")
        if self._subscribed:
            return
        self._loop = asyncio.get_running_loop()
        self._queue = asyncio.Queue(maxsize=_SUBSCRIBER_QUEUE_MAX)
        self._subscriber.subscribe(self._forward)
        self._subscribed = True

    def _forward(self, message: MsgT) -> None:
        # The QueueFull catch must run on the loop thread, where the put
        # actually executes — call_soon_threadsafe itself never raises.
        loop = self._loop
        if loop is not None:
            loop.call_soon_threadsafe(self._put_nowait, message)

    def _put_nowait(self, message: MsgT) -> None:
        queue = self._queue
        if self._closed or queue is None:
            return
        try:
            queue.put_nowait(message)
        except asyncio.QueueFull:
            pass

    def __aiter__(self) -> Self:
        """Return the async iterator (single-consumer stream)."""
        return self

    async def __anext__(self) -> MsgT:
        """Return the next message, subscribing on first use.

        Raises:
            StopAsyncIteration: After :meth:`aclose` — including a
                pending wait interrupted by ``aclose``.
        """
        if self._closed:
            raise StopAsyncIteration
        if not self._subscribed:
            await self.subscribe()
        queue = self._queue
        assert queue is not None, "queue is created by subscribe()"
        message = await queue.get()
        if message is None:
            raise StopAsyncIteration
        return message

    async def aclose(self) -> None:
        """Unsubscribe and end the stream.

        Idempotent — a pending ``__anext__`` wait is released with
        ``StopAsyncIteration`` and buffered messages are dropped.
        """
        if self._closed:
            return
        self._closed = True
        if self._subscribed:
            self._subscriber.unsubscribe()
            self._subscribed = False
        queue = self._queue
        if queue is not None:
            with suppress(asyncio.QueueFull):
                queue.put_nowait(_EOF)

    async def __aenter__(self) -> Self:
        """Enter the async context manager and subscribe eagerly."""
        await self.subscribe()
        return self

    async def __aexit__(self, *args: object) -> None:
        """Exit the async context manager and unsubscribe."""
        await self.aclose()


__all__ = ["AsyncSubscriber"]
