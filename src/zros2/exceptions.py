class ZRos2Exception(Exception):
    """Base exception for all zros2-related errors."""
    pass


class ServiceException(ZRos2Exception):
    """Base exception for ROS service errors."""
    pass


class ServiceNotAvailableException(ServiceException):
    """Exception raised when a ROS service is not available."""
    pass


class ServiceInvokeException(ServiceException):
    """Exception raised when a ROS service invocation fails."""
    pass


class ActionException(ZRos2Exception):
    """Base exception for ROS action errors."""
    pass


class ActionNotAvailableException(ActionException):
    """Exception raised when a ROS action is not available."""
    pass


class ActionInvokeException(ActionException):
    """Exception raised when a ROS action invocation fails."""
    pass
