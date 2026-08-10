"""Exception hierarchy for zros2.

All exceptions raised by the library inherit from ``ZRos2Exception``.
Downstream code can catch this base type or any of its specific subtypes.
"""

__all__ = [
    "ActionException",
    "ActionInvokeException",
    "ActionNotAvailableException",
    "ServiceException",
    "ServiceInvokeException",
    "ServiceNotAvailableException",
    "ZRos2Exception",
]


class ZRos2Exception(Exception):
    """Base exception for all zros2-related errors."""


class ServiceException(ZRos2Exception):
    """Base exception for ROS service errors."""


class ServiceNotAvailableException(ServiceException):
    """Exception raised when a ROS service is not available."""


class ServiceInvokeException(ServiceException):
    """Exception raised when a ROS service invocation fails."""


class ActionException(ZRos2Exception):
    """Base exception for ROS action errors."""


class ActionNotAvailableException(ActionException):
    """Exception raised when a ROS action is not available."""


class ActionInvokeException(ActionException):
    """Exception raised when a ROS action invocation fails."""
