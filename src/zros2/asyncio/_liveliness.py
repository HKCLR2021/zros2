"""Async liveliness bridge for zros2.

The core :mod:`zros2` package is synchronous: :class:`zros2.Liveliness`
blocks on ``get`` and delivers subscribe callbacks on Zenoh threads.
This module bridges that helper into asyncio — the blocking query is
offloaded with :func:`asyncio.to_thread` and liveliness changes are
forwarded into the event loop through a bounded queue — so
:class:`AsyncRobotClient` can expose them as awaitables / ``async for``.
"""

import asyncio
from collections.abc import AsyncGenerator

import zenoh

from .._session import ZenohSessionProxy
from ..discovery import Liveliness, LivelinessType, Qos

_LIVELINESS_QUEUE_MAX = 100


async def _query_liveliness(
    session: ZenohSessionProxy,
    entity: LivelinessType,
    name: str = "*",
    ros2_type: str = "*",
    qos: Qos | str | None = None,
    *,
    namespace: str = "",
) -> list[zenoh.Sample]:
    """Query currently alive matching entities on a worker thread.

    Args:
        session: The shared session proxy used for communication.
        entity: Entity type (a :class:`LivelinessType` member).
        name: Topic / service / action name (default ``"*"``).
        ros2_type: ROS type string (default ``"*"``).
        qos: QoS constraint (a :class:`Qos` instance or wildcard).
            Defaults to :meth:`Qos.any`.
        namespace: Device namespace.  Empty string means no namespace.

    Returns:
        One sample per currently alive matching entity.
    """
    full = f"{namespace}/{name.lstrip('/')}" if namespace else name
    liveliness = Liveliness(session, entity, full, ros2_type, qos)
    return await asyncio.to_thread(liveliness.get)


async def _watch_liveliness(
    session: ZenohSessionProxy,
    entity: LivelinessType,
    name: str = "*",
    ros2_type: str = "*",
    qos: Qos | str | None = None,
    *,
    namespace: str = "",
) -> AsyncGenerator[zenoh.Sample, None]:
    """Stream liveliness changes without blocking the event loop.

    Subscribes to matching entity liveliness tokens and yields a sample
    for every change.  Samples are dropped when the consumer is slower
    than the underlying liveliness stream (bounded queue, oldest entries
    first).  Only *changes* are reported — call :func:`_query_liveliness`
    for the current snapshot.  The subscription is undeclared when the
    generator is closed or the consumer breaks out of the ``async for``.

    Args:
        session: The shared session proxy used for communication.
        entity: Entity type (a :class:`LivelinessType` member).
        name: Topic / service / action name (default ``"*"``).
        ros2_type: ROS type string (default ``"*"``).
        qos: QoS constraint (a :class:`Qos` instance or wildcard).
            Defaults to :meth:`Qos.any`.
        namespace: Device namespace.  Empty string means no namespace.

    Yields:
        Sample: One liveliness sample per change.
    """
    loop = asyncio.get_running_loop()
    sample_queue: asyncio.Queue[zenoh.Sample] = asyncio.Queue(
        maxsize=_LIVELINESS_QUEUE_MAX
    )

    def _put_nowait(sample: zenoh.Sample) -> None:
        try:
            sample_queue.put_nowait(sample)
        except asyncio.QueueFull:
            pass

    def _forward(sample: zenoh.Sample) -> None:
        # The QueueFull catch must run on the loop thread, where the put
        # actually executes — call_soon_threadsafe itself never raises.
        loop.call_soon_threadsafe(_put_nowait, sample)

    full = f"{namespace}/{name.lstrip('/')}" if namespace else name
    liveliness = Liveliness(session, entity, full, ros2_type, qos)
    with liveliness:
        liveliness.subscribe(_forward)
        while True:
            yield await sample_queue.get()


__all__ = ["_query_liveliness", "_watch_liveliness"]
