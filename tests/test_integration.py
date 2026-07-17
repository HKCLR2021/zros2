"""Integration tests for zros2 communication primitives.

These tests use two local Zenoh peers — a server (listener) and a client
(connector) — operating in peer mode over the loopback interface to verify
end-to-end pub/sub, service, and action communication.
"""

import threading
import time

import pytest
import zenoh

from zros2 import ZRosClient, Publisher, Subscriber, ServiceClient

from ._test_msgs import ExampleService, IntMsg, PairMsg, StringMsg


# ── Helpers ──────────────────────────────────────────────────────────


def _wait_for_condition(
    cv: threading.Condition,
    predicate: ...,
    timeout: float = 5.0,
) -> bool:
    """Wait for a condition predicate to become true.

    Args:
        cv: A ``threading.Condition`` to wait on.
        predicate: A callable returning a truthy value.
        timeout: Maximum wait time in seconds.

    Returns:
        True if the predicate became true within the timeout.
    """
    with cv:
        return cv.wait_for(predicate, timeout=timeout)


# ── Publisher / Subscriber Tests ────────────────────────────────────


class TestPubSub:
    """Tests for :class:`Publisher` and :class:`Subscriber`."""

    def test_publish_and_receive(
        self,
        server_zros_client: ZRosClient,
        client_zros_client: ZRosClient,
    ) -> None:
        """Publish a message and verify the subscriber receives it."""
        received: list[StringMsg] = []
        cv = threading.Condition()

        def callback(msg: StringMsg) -> None:
            with cv:
                received.append(msg)
                cv.notify_all()

        topic = "test/integration/string"

        with (
            server_zros_client.create_subscriber(topic, StringMsg) as sub,
            client_zros_client.create_publisher(topic, StringMsg) as pub,
        ):
            sub.subscribe(callback)
            time.sleep(0.3)  # allow Zenoh to propagate the subscription

            pub.publish(StringMsg(data="hello world"))

            assert _wait_for_condition(cv, lambda: len(received) > 0), (
                "Timed out waiting for published message"
            )

        assert len(received) == 1
        assert received[0].data == "hello world"

    def test_publish_multiple_messages(
        self,
        server_zros_client: ZRosClient,
        client_zros_client: ZRosClient,
    ) -> None:
        """Publish several messages and verify all are received in order."""
        received: list[IntMsg] = []
        cv = threading.Condition()

        def callback(msg: IntMsg) -> None:
            with cv:
                received.append(msg)
                cv.notify_all()

        topic = "test/integration/multi_int"

        with (
            server_zros_client.create_subscriber(topic, IntMsg) as sub,
            client_zros_client.create_publisher(topic, IntMsg) as pub,
        ):
            sub.subscribe(callback)
            time.sleep(0.3)

            for i in range(5):
                pub.publish(IntMsg(data=i))

            assert _wait_for_condition(cv, lambda: len(received) >= 5), (
                f"Only received {len(received)}/5 messages"
            )

        assert [m.data for m in received] == [0, 1, 2, 3, 4]

    def test_subscriber_unsubscribe_stops_delivery(
        self,
        server_zros_client: ZRosClient,
        client_zros_client: ZRosClient,
    ) -> None:
        """Unsubscribing prevents further message delivery."""
        received: list[StringMsg] = []
        cv = threading.Condition()

        def callback(msg: StringMsg) -> None:
            with cv:
                received.append(msg)
                cv.notify_all()

        topic = "test/integration/unsub"

        with (
            server_zros_client.create_subscriber(topic, StringMsg) as sub,
            client_zros_client.create_publisher(topic, StringMsg) as pub,
        ):
            sub.subscribe(callback)
            time.sleep(0.3)

            pub.publish(StringMsg(data="before"))
            assert _wait_for_condition(cv, lambda: len(received) > 0)

            sub.unsubscribe()

            pub.publish(StringMsg(data="after"))
            time.sleep(0.5)  # give it time to NOT arrive

        assert len(received) == 1
        assert received[0].data == "before"

    def test_multiple_subscribers(
        self,
        server_zros_client: ZRosClient,
        client_zros_client: ZRosClient,
    ) -> None:
        """Multiple subscribers on the same topic all receive messages."""
        received_1: list[IntMsg] = []
        received_2: list[IntMsg] = []
        cv_1 = threading.Condition()
        cv_2 = threading.Condition()

        def callback_1(msg: IntMsg) -> None:
            with cv_1:
                received_1.append(msg)
                cv_1.notify_all()

        def callback_2(msg: IntMsg) -> None:
            with cv_2:
                received_2.append(msg)
                cv_2.notify_all()

        topic = "test/integration/multi_sub"

        with (
            server_zros_client.create_subscriber(topic, IntMsg) as sub1,
            client_zros_client.create_subscriber(topic, IntMsg) as sub2,
        ):
            sub1.subscribe(callback_1)
            sub2.subscribe(callback_2)
            time.sleep(0.3)

            # Create a separate publisher (using server side)
            with server_zros_client.create_publisher(topic, IntMsg) as pub:
                pub.publish(IntMsg(data=42))

            assert _wait_for_condition(cv_1, lambda: len(received_1) > 0)
            assert _wait_for_condition(cv_2, lambda: len(received_2) > 0)

        assert received_1[0].data == 42
        assert received_2[0].data == 42


# ── Service Client Tests ────────────────────────────────────────────


class TestService:
    """Tests for :class:`ServiceClient` with a queryable."""

    def test_service_request_response(
        self,
        server_zros_client: ZRosClient,
        client_zros_client: ZRosClient,
    ) -> None:
        """Send a service request and verify the response is received."""
        # Register a queryable (service handler) on the server side
        service_name = "test/integration/echo"

        def handler(query: zenoh.Query) -> None:
            payload = bytes(query.payload) if query.payload else b""
            request = IntMsg.deserialize(payload)
            response = PairMsg(value=request.data, label="ack")
            query.reply(service_name, response.serialize())

        session = server_zros_client.session
        queryable = session.declare_queryable(service_name, handler)
        try:
            time.sleep(0.3)  # allow Zenoh to propagate

            client = client_zros_client.create_srv_client(
                service_name, ExampleService,
            )
            result = client.send_request(IntMsg(data=99), timeout=3000)

            assert isinstance(result, PairMsg)
            assert result.value == 99
            assert result.label == "ack"
        finally:
            queryable.undeclare()

    def test_service_not_available(
        self,
        client_zros_client: ZRosClient,
    ) -> None:
        """Requesting a non-existent service raises an exception."""
        from zros2.exceptions import ServiceNotAvailableException

        client = client_zros_client.create_srv_client(
            "test/integration/nonexistent", ExampleService,
        )

        with pytest.raises(ServiceNotAvailableException):
            client.send_request(IntMsg(data=1), timeout=500)


# ── Multiple client sessions ────────────────────────────────────────


class TestTwoClients:
    """Tests that require two independently-created client pairs."""

    def test_cross_client_pub_sub(
        self,
        server_zros_client: ZRosClient,
        client_zros_client: ZRosClient,
        peer_port: int,
    ) -> None:
        """Publish from one client pair and subscribe from another.

        This test verifies that two separate ZRosClient instances
        (each backed by their own Zenoh session) can communicate.
        """
        import socket as _socket

        # Create a "client" config that connects to the existing server port
        client_config = zenoh.Config()
        client_config.insert_json5(
            "connect/endpoints", f'["tcp/127.0.0.1:{peer_port}"]'
        )
        client_config.insert_json5("mode", '"peer"')
        client_config.insert_json5("scouting/multicast/enabled", "false")

        extra_client = ZRosClient(config=client_config)

        received: list[PairMsg] = []
        cv = threading.Condition()

        def callback(msg: PairMsg) -> None:
            with cv:
                received.append(msg)
                cv.notify_all()

        topic = "test/integration/extra_client"

        with extra_client:
            with (
                server_zros_client.create_subscriber(topic, PairMsg) as sub,
                extra_client.create_publisher(topic, PairMsg) as pub,
            ):
                sub.subscribe(callback)
                time.sleep(0.3)

                pub.publish(PairMsg(value=7, label="extra"))

                assert _wait_for_condition(cv, lambda: len(received) > 0), (
                    "Timed out waiting for message from extra client"
                )

        assert received[0].value == 7
        assert received[0].label == "extra"
