"""Optional asyncio facade for zros2.

The core :mod:`zros2` package is synchronous.  This subpackage adapts
the threaded :class:`zros2.Action`, :class:`zros2.ServiceClient`, and
:class:`zros2.Publisher` / :class:`zros2.Subscriber` endpoints for
asyncio consumers — importing it does not change the sync core.
:class:`AsyncRobotClient` is the single entry point: it holds a
:class:`ZRosClient` (or session proxy) once, so calls never need to pass
the client around.  :class:`AsyncPublisher` / :class:`AsyncSubscriber`
wrap the pub/sub endpoints so blocking work runs on worker threads and
Zenoh-thread callbacks are bridged into the event loop.

Usage::

    from zros2 import ZRosClient
    from zros2.asyncio import AsyncRobotClient

    async def run(client: ZRosClient) -> None:
        zros = AsyncRobotClient(client)
        response = await zros.invoke_service("/trigger", Trigger)
        async for event in zros.invoke_action("/fib", Fibonacci):
            ...
"""

from ._action import ActionFeedback, ActionResult
from ._async_client import AsyncRobotClient
from ._publisher import AsyncPublisher
from ._subscriber import AsyncSubscriber

__all__ = [
    "ActionFeedback",
    "ActionResult",
    "AsyncPublisher",
    "AsyncRobotClient",
    "AsyncSubscriber",
]
