"""Async service invocation bridge for zros2.

The core :mod:`zros2` package is synchronous: :class:`zros2.ServiceClient`
blocks on ``send_request``.  This module offloads the blocking call with
:func:`asyncio.to_thread` so :class:`AsyncRobotClient` can await it from an
event loop.
"""

import asyncio

from .._session import ZenohSessionProxy
from ..endpoints._service import ServiceClient
from ..types._base import RosMessage
from ..types._protocols import RosService


async def _invoke_service[ReqT: RosMessage, ResT: RosMessage](
    session: ZenohSessionProxy,
    service_name: str,
    srv_type: type[RosService[ReqT, ResT]],
    body: ReqT | None = None,
    timeout: int | None = None,
    *,
    namespace: str = "",
) -> ResT:
    """Invoke a service on a worker thread and return the typed response.

    Args:
        session: The shared session proxy used for communication.
        service_name: Name of the service (without prefix).
        srv_type: The service type *class* (e.g. ``QueryTrajectory``).
        body: The request payload, or ``None`` for an empty request.
        timeout: Timeout in **milliseconds** for the service call.
            ``None`` waits indefinitely (default).
        namespace: Device namespace.  Empty string means no namespace.

    Returns:
        The response payload (``Response`` sub-type).

    Raises:
        ServiceInvokeException: If the service returns an error or a Zenoh
            communication error occurs.
        ServiceNotAvailableException: If no response is received.
    """
    full = f"{namespace}/{service_name.lstrip('/')}" if namespace else service_name
    service_client = ServiceClient(session, full, srv_type)
    return await asyncio.to_thread(service_client.send_request, body, timeout)


__all__ = ["_invoke_service"]
