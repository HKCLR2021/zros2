"""Service client — invoke ROS 2 services over Zenoh.

Serializes request payloads to CDR format, sends requests via Zenoh,
and deserializes responses into strongly typed dataclass instances.
"""

import itertools
from typing import Generic, cast

import zenoh

from .exceptions import ServiceInvokeException, ServiceNotAvailableException
from ._proxies import ZenohSessionProxy
from .types import RosService
from .types._base import _ReqT, _ResT


class ServiceClient(Generic[_ReqT, _ResT]):
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
            service_type: type[RosService[_ReqT, _ResT]],
    ):
        self._zenoh_session = zenoh_client
        self._service_name = service_name
        self._srv_types = service_type

    def send_request(
        self, payload: _ReqT | None, timeout: int = 1000
    ) -> _ResT:
        """Send a service request via Zenoh.

        Serializes the typed request dataclass to CDR, sends via Zenoh,
        and deserializes the response.

        Args:
            payload: The request message instance, or ``None`` for an
                empty request.
            timeout: Request timeout in **milliseconds** (default: 1000).

        Returns:
            Deserialized response message as a typed dataclass instance.

        Raises:
            RuntimeError: If Zenoh session is closed.
            ServiceInvokeException: If the service returns an error.
            ServiceNotAvailableException: If no response received.
        """
        if self._zenoh_session.is_closed():
            raise RuntimeError("Zenoh session is closed")

        cdr_payload = (
            payload.serialize() if payload is not None else None
        )

        try:
            replies = self._zenoh_session.get(
                self._service_name,
                payload=cdr_payload,
                timeout=timeout,
            )
            for reply in itertools.islice(replies, 1):
                reply: zenoh.Reply
                if reply.ok:
                    response = cast(
                        _ResT,
                        self._srv_types.Response.deserialize(
                            bytes(reply.ok.payload)
                        ),
                    )
                    return response
                else:
                    err = reply.err
                    assert err is not None, "reply.err must be set when reply.ok is falsy"
                    error = err.payload
                    raise ServiceInvokeException(
                        f"Service error occurred: {error.to_string()}"
                    )
            else:
                raise ServiceNotAvailableException(
                    "The requested service is not available"
                )
        except zenoh.ZError as e:
            raise ServiceInvokeException(
                f"Zenoh communication error: {e}"
            ) from e
