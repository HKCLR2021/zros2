"""Proxy wrapper for Zenoh sessions.

``ZenohSessionProxy`` provides a safe read-only wrapper around a Zenoh
session that prevents accidental closure or undeclaration of resources
by components that only need read access to the session.
"""

from typing import Any

import zenoh


class ZenohSessionProxy:
    """Safe read-only proxy that prevents closing the underlying Zenoh session.

    This proxy forwards all attribute accesses to the wrapped zenoh.Session
    object, but explicitly blocks calls to methods that could terminate or
    corrupt the session (e.g., ``close``, ``destroy``). The proxy is intended
    to be shared among multiple components that need to use the session but
    must never shut it down.
    """

    def __init__(self, session: zenoh.Session):
        """Wrap a Zenoh session in a protective proxy.

        Args:
            session: The native zenoh.Session object to protect.
        """
        # Bypass __setattr__ to store the real session.
        self.__dict__["_session"] = session

    def __getattr__(self, name: str):
        """Delegate attribute access to the underlying session.

        Raises:
            PermissionError: If the requested attribute is in the forbidden
                list (``close``, ``destroy``, ``__del__``, ``undeclare``).
        """
        # Intercept any call that could compromise the session.
        forbidden = {"close", "destroy", "__del__", "undeclare"}
        if name in forbidden:
            raise PermissionError(
                f"Calling '{name}' is forbidden. The session is borrowed."
            )
        return getattr(self._session, name)

    def __setattr__(self, name: str, value: Any):
        """Prevent any mutation of the proxy instance.

        This ensures that external code cannot monkey-patch a dangerous
        method like ``close`` onto the proxy, e.g.,
        ``proxy.close = lambda: None``.

        Raises:
            PermissionError: Always raised to block modification.
        """
        raise PermissionError("Modifying the session proxy is not allowed.")

    def __del__(self):
        """Do nothing on deletion.

        This guarantees that destroying the proxy does not accidentally
        close the underlying Zenoh session.
        """
        pass  # The real session outlives the proxy.
