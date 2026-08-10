"""Protected access to a shared Zenoh session."""

from typing import Any, override

import zenoh


class ZenohSessionProxy:
    """Read-only proxy that prevents closing the underlying Zenoh session."""

    def __init__(self, session: zenoh.Session):
        """Wrap a Zenoh session in a protective proxy.

        Args:
            session: Native Zenoh session to protect.
        """
        self.__dict__["_session"] = session

    def __getattr__(self, name: str) -> Any:
        """Delegate safe attribute access to the underlying session.

        Raises:
            PermissionError: If the requested operation could close or
                undeclare the shared session.
        """
        forbidden = {"close", "destroy", "__del__", "undeclare"}
        if name in forbidden:
            raise PermissionError(
                f"Calling '{name}' is forbidden. The session is borrowed."
            )
        return getattr(self._session, name)

    @override
    def __setattr__(self, name: str, value: object) -> None:
        """Prevent mutation of the proxy."""
        raise PermissionError("Modifying the session proxy is not allowed.")

    def __del__(self) -> None:
        """Leave the independently owned session untouched."""


__all__ = ["ZenohSessionProxy"]
