"""Normalize ROS graph names into valid Zenoh key expressions."""


def normalize_namespace(namespace: str) -> str:
    """Normalize a namespace for use as a Zenoh key-expression prefix.

    ROS namespaces are conventionally written with a leading slash
    (``/robot_01``), while Zenoh key expressions must not start or end with
    one.  Empty namespaces are allowed and mean "no prefix".

    Args:
        namespace: Device namespace, with or without surrounding slashes.

    Returns:
        The normalized namespace, or ``""`` when no namespace was given.

    Raises:
        TypeError: If ``namespace`` is not a string.
        ValueError: If the namespace contains an empty path chunk.
    """
    if not isinstance(namespace, str):
        raise TypeError(f"namespace must be str, got {type(namespace).__name__}")

    normalized = namespace.strip().strip("/")
    if "//" in normalized:
        raise ValueError(f"Invalid namespace {namespace!r}: empty path chunk")
    return normalized


def normalize_graph_name(name: str) -> str:
    """Normalize a single ROS graph name for use as a Zenoh key expression.

    Both ROS 2 and the Zenoh ROS 2 bridge address entities without a leading
    slash on the Zenoh side: ROS ``/chatter`` maps to Zenoh ``chatter``.  This
    function accepts either spelling and returns the Zenoh-side form.

    Args:
        name: Topic, service, or action name.

    Returns:
        The name without leading or trailing slashes.

    Raises:
        TypeError: If ``name`` is not a string.
        ValueError: If ``name`` is empty or contains an empty path chunk.
    """
    if not isinstance(name, str):
        raise TypeError(f"name must be str, got {type(name).__name__}")

    normalized = name.strip().strip("/")
    if not normalized:
        raise ValueError("Graph name must not be empty")
    if "//" in normalized:
        raise ValueError(f"Invalid graph name {name!r}: empty path chunk")
    return normalized


def join_name(namespace: str, name: str) -> str:
    """Join a device namespace with a ROS graph name.

    Both inputs are normalized, so ``join_name("", "/chatter")`` and
    ``join_name("robot_01", "/chatter")`` produce valid Zenoh keys
    (``"chatter"`` and ``"robot_01/chatter"`` respectively).

    Args:
        namespace: Device namespace.  Empty string means no namespace.
        name: Topic, service, or action name.

    Returns:
        The normalized, fully qualified Zenoh key.
    """
    ns = normalize_namespace(namespace)
    graph_name = normalize_graph_name(name)
    return f"{ns}/{graph_name}" if ns else graph_name


__all__ = ["join_name", "normalize_graph_name", "normalize_namespace"]
