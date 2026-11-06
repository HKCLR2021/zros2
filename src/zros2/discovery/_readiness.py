"""Service readiness probes based on Zenoh liveliness tokens."""

import time

from zros2._namespace import join_name
from zros2._session import ZenohSessionProxy

from ._liveliness import Liveliness, LivelinessType

_SERVICE_POLL_INTERVAL = 0.1


def service_is_ready(
    session: ZenohSessionProxy,
    service_name: str,
    ros2_type: str,
    *,
    namespace: str = "",
) -> bool:
    """Return whether a service server with this name and type is alive."""
    liveliness = Liveliness(
        session,
        LivelinessType.SERVICE_SERVER,
        join_name(namespace, service_name),
        ros2_type,
    )
    return bool(liveliness.get(timeout_ms=0))


def wait_for_service(
    session: ZenohSessionProxy,
    service_name: str,
    ros2_type: str,
    timeout_ms: int | None = None,
    *,
    namespace: str = "",
) -> bool:
    """Block until a matching service server appears, or the timeout expires."""
    liveliness = Liveliness(
        session,
        LivelinessType.SERVICE_SERVER,
        join_name(namespace, service_name),
        ros2_type,
    )
    if timeout_ms is None:
        while not liveliness.get():
            time.sleep(_SERVICE_POLL_INTERVAL)
        return True
    deadline = time.monotonic() + timeout_ms / 1000.0
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return bool(liveliness.get(timeout_ms=0))
        if liveliness.get(timeout_ms=min(1000, max(1, int(remaining * 1000)))):
            return True
        time.sleep(min(_SERVICE_POLL_INTERVAL, max(0.0, remaining)))


__all__ = ["service_is_ready", "wait_for_service"]
