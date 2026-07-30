"""Unit tests for :mod:`zros2.discovery` pure-logic components.

Tests cover :class:`Qos`, :class:`LivelinessKey`, and the
:data:`_ENTITY_BUILDER` mapping — all of which are pure Python and
do not require a real Zenoh session.
"""

from unittest.mock import MagicMock

import pytest

from zros2.discovery._key import LivelinessKey
from zros2.discovery._liveliness import _ENTITY_BUILDER, Liveliness, LivelinessType
from zros2.discovery._qos import Qos

# ======================================================================
# Qos.to_key_expr
# ======================================================================


class TestQosToKeyExpr:
    def test_default_keyless(self):
        """Default Qos with keyless=True produces '::::'."""
        qos = Qos()
        assert qos.to_key_expr(keyless=True) == ":::"

    def test_keyed_emits_K(self):
        """keyless=False should emit 'K' at the start."""
        qos = Qos()
        assert qos.to_key_expr(keyless=False).startswith("K")

    def test_with_reliability(self):
        """Reliability value should appear in the second segment."""
        qos = Qos(reliability=1)
        assert qos.to_key_expr() == ":1::"

    def test_with_durability(self):
        """Durability value should appear in the third segment."""
        qos = Qos(durability=2)
        assert qos.to_key_expr() == "::2:"

    def test_with_history(self):
        """History kind and depth should appear in the fourth segment."""
        qos = Qos(history_kind=3, history_depth=10)
        assert qos.to_key_expr() == ":::3,10"

    def test_with_user_data(self):
        """User data should appear as an appended segment."""
        qos = Qos(user_data=b"hello")
        result = qos.to_key_expr()
        assert result == "::::hello"

    def test_all_fields(self):
        """All fields filled should produce a full key expression."""
        qos = Qos(
            reliability=1,
            durability=2,
            history_kind=3,
            history_depth=10,
            user_data=b"test",
        )
        assert qos.to_key_expr() == ":1:2:3,10:test"
        assert qos.to_key_expr(keyless=False) == "K:1:2:3,10:test"


# ======================================================================
# Qos.from_key_expr
# ======================================================================


class TestQosFromKeyExpr:
    def test_empty_ke(self):
        """An empty key expression returns keyless=True, empty Qos."""
        keyless, qos = Qos.from_key_expr(":::")
        assert keyless is True
        assert qos.reliability is None
        assert qos.durability is None

    def test_keyed_ke(self):
        """A key expression starting with 'K' returns keyless=False."""
        keyless, _qos = Qos.from_key_expr("K:::")
        assert keyless is False

    def test_with_reliability(self):
        """Second segment sets reliability."""
        _, qos = Qos.from_key_expr(":1::")
        assert qos.reliability == 1

    def test_with_durability(self):
        """Third segment sets durability."""
        _, qos = Qos.from_key_expr("::2:")
        assert qos.durability == 2

    def test_with_history(self):
        """Fourth segment with comma sets history kind and depth."""
        _, qos = Qos.from_key_expr(":::3,10")
        assert qos.history_kind == 3
        assert qos.history_depth == 10

    def test_with_history_kind_only(self):
        """Fourth segment without comma sets history kind only."""
        _, qos = Qos.from_key_expr(":::5")
        assert qos.history_kind == 5
        assert qos.history_depth is None

    def test_with_user_data(self):
        """Fifth segment sets user data."""
        _, qos = Qos.from_key_expr("::::hello")
        assert qos.user_data == b"hello"

    def test_roundtrip(self):
        """to_key_expr followed by from_key_expr should roundtrip."""
        original = Qos(
            reliability=1,
            durability=2,
            history_kind=3,
            history_depth=10,
            user_data=b"test",
        )
        ke = original.to_key_expr(keyless=False)
        keyless, restored = Qos.from_key_expr(ke)
        assert keyless is False
        assert restored.reliability == original.reliability
        assert restored.durability == original.durability
        assert restored.history_kind == original.history_kind
        assert restored.history_depth == original.history_depth
        assert restored.user_data == original.user_data


# ======================================================================
# Qos.any
# ======================================================================


class TestQosAny:
    def test_returns_wildcard(self):
        """Qos.any() should return '*'."""
        assert Qos.any() == "*"


# ======================================================================
# LivelinessKey — escape/unescape
# ======================================================================


class TestLivelinessKeyEscape:
    def test_escape_slashes(self):
        """Forward slashes should be replaced with the replacement char."""
        result = LivelinessKey._escape_slashes("a/b/c")
        assert "/" not in result
        assert len(result) == 5
        assert "§" in result

    def test_unescape_slashes(self):
        """Replacement char should be restored to forward slashes."""
        escaped = LivelinessKey._escape_slashes("a/b/c")
        restored = LivelinessKey._unescape_slashes(escaped)
        assert restored == "a/b/c"

    def test_no_slashes(self):
        """Strings without slashes should pass through unchanged."""
        assert LivelinessKey._escape_slashes("plain") == "plain"
        assert LivelinessKey._unescape_slashes("plain") == "plain"


# ======================================================================
# LivelinessKey — builders
# ======================================================================


class TestLivelinessKeyBuilders:
    def test_build_all_ke(self):
        """build_all_ke should use the wildcard template."""
        ke = LivelinessKey.build_all_ke("my_id")
        assert ke == "@/my_id/@ros2_lv/**"

    def test_build_all_ke_default_id(self):
        """build_all_ke without arguments should use '*'."""
        ke = LivelinessKey.build_all_ke()
        assert ke == "@/*/@ros2_lv/**"

    def test_build_plugin_ke(self):
        """build_plugin_ke should use the plugin template."""
        ke = LivelinessKey.build_plugin_ke("my_id")
        assert ke == "@/my_id/@ros2_lv"

    def test_build_publisher_ke_with_qos(self):
        """build_publisher_ke with Qos should include encoded QoS."""
        qos = Qos(reliability=1)
        ke = LivelinessKey.build_publisher_ke("my_id", "topic", "pkg/Msg", qos=qos)
        assert ke.startswith("@/my_id/@ros2_lv/MP/")
        assert "pkg§Msg" in ke
        assert ":1::" in ke

    def test_build_publisher_ke_with_qos_wildcard(self):
        """build_publisher_ke with Qos.any() should include '*'."""
        ke = LivelinessKey.build_publisher_ke("my_id", "topic", "pkg/Msg", qos="*")
        assert ke.endswith("*")

    def test_build_publisher_ke_without_qos(self):
        """build_publisher_ke with qos=None should use default empty Qos."""
        ke = LivelinessKey.build_publisher_ke("my_id", "topic", "pkg/Msg", qos=None)
        assert ":::" in ke  # default empty QoS

    def test_build_publisher_ke_escapes_slashes(self):
        """Topic and type slashes should be escaped in the KE."""
        ke = LivelinessKey.build_publisher_ke("my_id", "a/b", "x/y")
        assert "a§b" in ke
        assert "x§y" in ke

    def test_build_subscriber_ke(self):
        """build_subscriber_ke should use the MS prefix."""
        qos = Qos(durability=2)
        ke = LivelinessKey.build_subscriber_ke("my_id", "topic", "pkg/Msg", qos=qos)
        assert "@" in ke
        assert "/MS/" in ke

    def test_build_service_server_ke(self):
        """build_service_server_ke should use the SS prefix."""
        ke = LivelinessKey.build_service_server_ke("my_id", "srv_name", "pkg/Srv")
        assert "/SS/" in ke
        assert "srv_name" in ke

    def test_build_service_client_ke(self):
        """build_service_client_ke should use the SC prefix."""
        ke = LivelinessKey.build_service_client_ke("my_id", "srv_name", "pkg/Srv")
        assert "/SC/" in ke

    def test_build_action_server_ke(self):
        """build_action_server_ke should use the AS prefix."""
        ke = LivelinessKey.build_action_server_ke("my_id", "act_name", "pkg/Act")
        assert "/AS/" in ke

    def test_build_action_client_ke(self):
        """build_action_client_ke should use the AC prefix."""
        ke = LivelinessKey.build_action_client_ke("my_id", "act_name", "pkg/Act")
        assert "/AC/" in ke


# ======================================================================
# LivelinessKey — parsers
# ======================================================================


class TestLivelinessKeyParsers:
    def test_parse_publisher_ke_roundtrip(self):
        """Parse a publisher KE should recover all fields."""
        original_ke = "@/my_id/@ros2_lv/MP/topic§name/pkg§Msg/:::"
        zenoh_id, topic, ros2_type, keyless, _qos = LivelinessKey.parse_publisher_ke(
            original_ke
        )
        assert zenoh_id == "my_id"
        assert topic == "topic/name"
        assert ros2_type == "pkg/Msg"
        assert keyless is True

    def test_parse_subscriber_ke(self):
        """Parse a subscriber KE."""
        ke = "@/dev_1/@ros2_lv/MS/my§topic/str§Msg/:1::"
        zenoh_id, topic, ros2_type, _keyless, qos = LivelinessKey.parse_subscriber_ke(
            ke
        )
        assert zenoh_id == "dev_1"
        assert topic == "my/topic"
        assert ros2_type == "str/Msg"
        assert qos.reliability == 1

    def test_parse_service_server_ke(self):
        """Parse a service server KE."""
        ke = "@/dev_1/@ros2_lv/SS/echo/pkg§Srv"
        zenoh_id, srv_name, ros2_type = LivelinessKey.parse_service_server_ke(ke)
        assert zenoh_id == "dev_1"
        assert srv_name == "echo"
        assert ros2_type == "pkg/Srv"

    def test_parse_service_client_ke(self):
        """Parse a service client KE."""
        ke = "@/dev_1/@ros2_lv/SC/echo/pkg§Srv"
        zenoh_id, _srv_name, _ros2_type = LivelinessKey.parse_service_client_ke(ke)
        assert zenoh_id == "dev_1"

    def test_parse_action_server_ke(self):
        """Parse an action server KE."""
        ke = "@/dev_1/@ros2_lv/AS/fib/pkg§Action"
        _zenoh_id, act_name, _ros2_type = LivelinessKey.parse_action_server_ke(ke)
        assert act_name == "fib"

    def test_parse_action_client_ke(self):
        """Parse an action client KE."""
        ke = "@/dev_1/@ros2_lv/AC/fib/pkg§Action"
        _zenoh_id, act_name, _ros2_type = LivelinessKey.parse_action_client_ke(ke)
        assert act_name == "fib"

    def test_parse_invalid_ke_raises(self):
        """A KE without the expected structure should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid liveliness"):
            LivelinessKey._split_ke("invalid", "MP", 5)

    def test_parse_wrong_prefix_raises(self):
        """A KE with the wrong prefix should raise ValueError."""
        ke = "@/id/@ros2_lv/WRONG/topic/type"
        with pytest.raises(ValueError, match="Expected prefix"):
            LivelinessKey._split_ke(ke, "MP", 6)

    def test_parse_too_short_ke_raises(self):
        """A KE that is too short should raise ValueError."""
        ke = "@/id/@ros2_lv/MP/topic/type"
        with pytest.raises(ValueError, match="Expected at least"):
            LivelinessKey._split_ke(ke, "MP", 7)


# ======================================================================
# _ENTITY_BUILDER mapping
# ======================================================================


class TestEntityBuilder:
    def test_known_entities_have_builders(self):
        """All entity types that need builders should have one.

        Note: ``LivelinessType.ALL`` and ``LivelinessType.PLUGIN`` are
        not in the builder dict since they don't correspond to a single
        entity type with topic/name/type parameters.
        """
        for entity in (
            LivelinessType.PUBLISHER,
            LivelinessType.SUBSCRIBER,
            LivelinessType.SERVICE_SERVER,
            LivelinessType.SERVICE_CLIENT,
            LivelinessType.ACTION_SERVER,
            LivelinessType.ACTION_CLIENT,
        ):
            assert entity in _ENTITY_BUILDER, f"{entity} missing from _ENTITY_BUILDER"

    def test_each_builder_returns_string(self):
        """Each builder should produce a valid KE string."""
        for entity, builder in _ENTITY_BUILDER.items():
            if entity in (LivelinessType.PUBLISHER, LivelinessType.SUBSCRIBER):
                result = builder("id", "topic", "type", qos="*")
            else:
                result = builder("id", "name", "type")
            assert isinstance(result, str)
            assert result.startswith("@")


# ======================================================================
# Liveliness class (requires mocked Zenoh session proxy)
# ======================================================================


class TestLivelinessClass:
    """Tests for :class:`zros2.discovery._liveliness.Liveliness`."""

    def test_unsupported_entity_raises_value_error(self):
        """Passing an entity type not in _ENTITY_BUILDER should raise ValueError."""
        session = MagicMock()
        with pytest.raises(ValueError, match="Unsupported entity type"):
            Liveliness(session, LivelinessType.ALL)  # ALL is not in builder

    def test_no_qos_defaults_to_any(self):
        """When qos is None, it defaults to Qos.any() which returns '*'."""
        session = MagicMock()
        liv = Liveliness(
            session, LivelinessType.SERVICE_SERVER, name="echo", ros2_type="pkg/Srv"
        )
        # No qos → Qos.any() which produces '*' appended to the KE.
        assert liv._ke is not None
        assert "echo" in liv._ke

    def test_publisher_entity_uses_qos(self):
        """PUBLISHER entity builds a KE with QoS parameter."""
        session = MagicMock()
        liv = Liveliness(
            session,
            LivelinessType.PUBLISHER,
            name="my_topic",
            ros2_type="pkg/Msg",
            qos=Qos(reliability=1),
        )
        assert "/MP/" in liv._ke
        assert ":1::" in liv._ke

    def test_subscriber_entity_uses_qos(self):
        """SUBSCRIBER entity builds a KE with QoS parameter."""
        session = MagicMock()
        liv = Liveliness(
            session,
            LivelinessType.SUBSCRIBER,
            name="my_topic",
            ros2_type="pkg/Msg",
            qos=Qos(durability=2),
        )
        assert "/MS/" in liv._ke
        assert "::2:" in liv._ke

    def test_service_server_entity_no_qos(self):
        """Service / action entities build KE without QoS parameter."""
        session = MagicMock()
        liv = Liveliness(
            session,
            LivelinessType.SERVICE_SERVER,
            name="echo",
            ros2_type="pkg/Srv",
        )
        assert "/SS/" in liv._ke
        assert "echo" in liv._ke

    def test_action_client_entity(self):
        """Action client entity builds KE correctly."""
        session = MagicMock()
        liv = Liveliness(
            session,
            LivelinessType.ACTION_CLIENT,
            name="fib",
            ros2_type="pkg/Act",
        )
        assert "/AC/" in liv._ke
        assert "fib" in liv._ke

    def test_context_manager(self):
        """Liveliness can be used as a context manager."""
        session = MagicMock()
        with Liveliness(session, LivelinessType.SERVICE_SERVER, name="echo") as liv:
            assert liv is not None
        # __exit__ calls close → _close_subscriber → no-op (sub is None)

    def test_close_subscriber_when_sub_is_none(self):
        """_close_subscriber is idempotent when _sub is None."""
        session = MagicMock()
        liv = Liveliness(session, LivelinessType.SERVICE_SERVER, name="echo")
        liv._close_subscriber()  # Should not raise
        assert liv._sub is None

    def test_close_subscriber_swallows_exception(self):
        """_close_subscriber catches and logs exceptions from undeclare."""
        session = MagicMock()
        liv = Liveliness(session, LivelinessType.SERVICE_SERVER, name="echo")
        liv._sub = MagicMock()
        liv._sub.undeclare.side_effect = RuntimeError("boom")
        liv._close_subscriber()  # Should not raise
        assert liv._sub is None

    def test_close_calls_close_subscriber(self):
        """close() delegates to _close_subscriber."""
        session = MagicMock()
        liv = Liveliness(session, LivelinessType.SERVICE_SERVER, name="echo")
        liv._sub = MagicMock()
        liv.close()
        assert liv._sub is None

    def test_get_returns_samples(self):
        """``get()`` calls ``zenoh_session.liveliness().get()`` and returns samples.

        Covers line 55 in ``_liveliness.py``.
        """
        session = MagicMock()
        # Mock the liveliness chain: session.liveliness().get(ke) returns an iterable
        mock_sample = MagicMock()
        mock_sample.key_expr = "test/ke"
        session.liveliness.return_value.get.return_value = iter([mock_sample])

        liv = Liveliness(session, LivelinessType.SERVICE_SERVER, name="echo")
        results = liv.get()
        assert len(results) == 1
        assert results[0].key_expr == "test/ke"
        session.liveliness.return_value.get.assert_called_once_with(liv._ke)

    def test_subscribe_returns_subscriber(self):
        """``subscribe()`` calls ``declare_subscriber`` and returns the subscriber.

        Covers lines 69-73 in ``_liveliness.py``.
        """
        session = MagicMock()
        mock_sub = MagicMock()
        session.liveliness.return_value.declare_subscriber.return_value = mock_sub

        liv = Liveliness(session, LivelinessType.SERVICE_SERVER, name="echo")
        callback = lambda s: None
        result = liv.subscribe(callback)
        assert result is mock_sub
        assert liv._sub is mock_sub
        session.liveliness.return_value.declare_subscriber.assert_called_once_with(
            liv._ke, callback
        )

    def test_get_returns_empty_list_when_no_entities(self):
        """``get()`` returns an empty list when no matching entities exist."""
        session = MagicMock()
        session.liveliness.return_value.get.return_value = iter([])

        liv = Liveliness(session, LivelinessType.SERVICE_SERVER, name="echo")
        results = liv.get()
        assert results == []

    def test_subscribe_replaces_existing_subscriber(self):
        """``subscribe()`` closes any existing subscriber before creating a new one."""
        session = MagicMock()
        old_sub = MagicMock()
        new_sub = MagicMock()
        session.liveliness.return_value.declare_subscriber.return_value = new_sub

        liv = Liveliness(session, LivelinessType.SERVICE_SERVER, name="echo")
        liv._sub = old_sub

        callback = lambda s: None
        result = liv.subscribe(callback)
        assert result is new_sub
        assert liv._sub is new_sub
        old_sub.undeclare.assert_called_once()
