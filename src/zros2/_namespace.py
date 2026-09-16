"""Join a device namespace with a topic, service, or action name."""


def join_name(namespace: str, name: str) -> str:
    """Join a device namespace with a ROS graph name.

    Empty ``namespace`` leaves ``name`` unchanged.  A leading slash on
    ``name`` is stripped when a namespace is applied.

    Args:
        namespace: Device namespace.  Empty string means no namespace.
        name: Topic, service, or action name.

    Returns:
        The fully qualified name.
    """
    if not namespace:
        return name
    return f"{namespace}/{name.lstrip('/')}"


__all__ = ["join_name"]
