"""Service client endpoint for invoking ROS 2 services over Zenoh."""

import itertools

import zenoh

from .._session import ZenohSessionProxy
from ..exceptions import ServiceInvokeException, ServiceNotAvailableException
from ..types import RosMessage, RosService


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
        service_type: type[RosService[ReqT, ResT]],
    ):
        self._zenoh_session = zenoh_client
        self._service_name = service_name
        self._srv_types = service_type

    def send_request(self, payload: ReqT | None, timeout: int = 1000) -> ResT:
        """Send a service request via Zenoh.

        Args:
            payload: The request message instance, or ``None`` for an empty request.
            timeout: Request timeout in milliseconds.

        Returns:
            Deserialized response message.

        Raises:
            RuntimeError: If Zenoh session is closed.
            ServiceInvokeException: If the service returns an error.
            ServiceNotAvailableException: If no response is received.
        """
        if self._zenoh_session.is_closed():
            raise RuntimeError("Zenoh session is closed")

        cdr_payload = payload.serialize() if payload is not None else None

        try:
            replies = self._zenoh_session.get(
                self._service_name,
                payload=cdr_payload,
                timeout=timeout,
            )
            for reply in itertools.islice(replies, 1):
                if reply.ok:
                    return self._srv_types.Response.deserialize(bytes(reply.ok.payload))

                err = reply.err
                assert err is not None, "reply.err must be set when reply.ok is falsy"
                raise ServiceInvokeException(
                    f"Service error occurred: {err.payload.to_string()}"
                )

            raise ServiceNotAvailableException("The requested service is not available")
        except zenoh.ZError as error:
            raise ServiceInvokeException(
                f"Zenoh communication error: {error}"
            ) from error


__all__ = ["ServiceClient"]
