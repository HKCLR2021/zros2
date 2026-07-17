"""pytest configuration for zros2 tests.

Provides fixtures for Zenoh-based integration testing with local peers
operating over the loopback interface (``tcp/127.0.0.1``).

The setup uses a **client-server** topology within a single process:
one session listens on a dynamically assigned port while the other
connects to it.  This avoids reliance on UDP multicast and works
reliably on any system with a functional loopback interface.
"""

import socket
from collections.abc import Generator
from typing import Any

import pytest
import zenoh

from zros2 import ZRosClient


def _find_free_port() -> int:
    """Return a free TCP port on loopback."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _make_server_config(port: int) -> zenoh.Config:
    """Create a Zenoh peer config that listens on a specific port.

    Multicast scouting is disabled so the peer only accepts incoming
    connections via the explicit TCP listener.
    """
    config = zenoh.Config()
    config.insert_json5("mode", '"peer"')
    config.insert_json5("listen/endpoints", f'["tcp/127.0.0.1:{port}"]')
    config.insert_json5("scouting/multicast/enabled", "false")
    return config


def _make_client_config(port: int) -> zenoh.Config:
    """Create a Zenoh peer config that connects to a specific listener port.

    This peer does not listen; it only initiates an outgoing connection.
    """
    config = zenoh.Config()
    config.insert_json5("mode", '"peer"')
    config.insert_json5("connect/endpoints", f'["tcp/127.0.0.1:{port}"]')
    config.insert_json5("scouting/multicast/enabled", "false")
    return config


# ── Session-level fixtures ──────────────────────────────────────────


@pytest.fixture(scope="session")
def peer_port() -> int:
    """Determine a free TCP port for the Zenoh listener session.

    The port is chosen once per test session and reused for all tests.
    """
    return _find_free_port()


@pytest.fixture(scope="session")
def server_zenoh_config(peer_port: int) -> zenoh.Config:
    """Zenoh config for the listening (server) peer."""
    return _make_server_config(peer_port)


@pytest.fixture(scope="session")
def client_zenoh_config(peer_port: int) -> zenoh.Config:
    """Zenoh config for the connecting (client) peer."""
    return _make_client_config(peer_port)


@pytest.fixture(scope="session")
def server_session(
    server_zenoh_config: zenoh.Config,
) -> Generator[zenoh.Session, Any, None]:
    """Open the listening Zenoh session (server side)."""
    session = zenoh.open(server_zenoh_config)
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="session")
def client_session(
    client_zenoh_config: zenoh.Config,
) -> Generator[zenoh.Session, Any, None]:
    """Open the connecting Zenoh session (client side)."""
    session = zenoh.open(client_zenoh_config)
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="session")
def server_zros_client(
    server_zenoh_config: zenoh.Config,
) -> Generator[ZRosClient, Any, None]:
    """ZRosClient wrapping the server-side Zenoh session."""
    with ZRosClient(config=server_zenoh_config) as client:
        yield client


@pytest.fixture(scope="session")
def client_zros_client(
    client_zenoh_config: zenoh.Config,
) -> Generator[ZRosClient, Any, None]:
    """ZRosClient wrapping the client-side Zenoh session."""
    with ZRosClient(config=client_zenoh_config) as client:
        yield client
