"""Service client endpoint for invoking ROS 2 services over Zenoh."""

import itertools

import zenoh

from zros2._namespace import normalize_graph_name
from zros2._session import ZenohSessionProxy
from zros2.exceptions import (
    ServiceInvokeException,
    ServiceNotAvailableException,
    ServiceTimeoutException,
)
from zros2.types._base import RosMessage
from zros2.types._protocols import RosService


class ServiceClient[ReqT: RosMessage, ResT: RosMessage]:
    """Client for invoking ROS services over Zenoh.

    Args:
        zenoh_client: Active Zenoh session.
        service_name: Fully qualified ROS service name.
        service_type: Resolved service type with ``.Request`` and ``.Response``.
    """

    def __init__(
        self,
        zenoh_client: ZenohSessionProxy,
        service_name: str,
        service_type: RosService[ReqT, ResT],
    ):
        self._zenoh_session = zenoh_client
        self._service_name = normalize_graph_name(service_name)
        self._srv_types = service_type

    def send_request(
        self,
        payload: ReqT | None,
        timeout: int | None = 1000,
        cancellation_token: zenoh.CancellationToken | None = None,
    ) -> ResT:
        """Send a service request via Zenoh.

        Args:
            payload: The request message instance, or ``None`` for an empty request.
            timeout: Request timeout in **milliseconds**.  ``None`` waits
                indefinitely (default: 1000).
            cancellation_token: Optional Zenoh cancellation token, used by
                the asyncio facade to stop a worker thread on cancellation.

        Returns:
            Deserialized response message.

        Raises:
            RuntimeError: If Zenoh session is closed.
            ServiceInvokeException: If the service returns an error.
            ServiceNotAvailableException: If no service is available.
            ServiceTimeoutException: If a service exists but does not reply
                within *timeout*.
        """
        if self._zenoh_session.is_closed():
            raise RuntimeError("Zenoh session is closed")

        cdr_payload = payload.serialize() if payload is not None else None

        try:
            replies = self._zenoh_session.get(
                self._service_name,
                payload=cdr_payload,
                timeout=timeout,
                cancellation_token=cancellation_token,
            )
            for reply in itertools.islice(replies, 1):
                if reply.ok:
                    return self._srv_types.Response.deserialize(bytes(reply.ok.payload))

                err = reply.err
                if err is None:
                    raise ServiceInvokeException(
                        "Service returned an error reply without error details"
                    )
                raise ServiceInvokeException(
                    f"Service error occurred: {err.payload.to_string()}"
                )

            if timeout is not None:
                raise ServiceTimeoutException(
                    f"Service request timed out after {timeout} ms"
                )
            raise ServiceNotAvailableException("The requested service is not available")
        except zenoh.ZError as error:
            raise ServiceInvokeException(
                f"Zenoh communication error: {error}"
            ) from error


__all__ = ["ServiceClient"]
