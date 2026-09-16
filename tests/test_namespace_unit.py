"""Tests for ``zros2._namespace.join_name``."""

from zros2._namespace import join_name


class TestJoinName:
    def test_empty_namespace_preserves_name(self):
        assert join_name("", "/chatter") == "/chatter"
        assert join_name("", "chatter") == "chatter"

    def test_joins_namespace(self):
        assert join_name("robot_01", "chatter") == "robot_01/chatter"

    def test_strips_leading_slash_on_name(self):
        assert join_name("robot_01", "/chatter") == "robot_01/chatter"

    def test_wildcard_name(self):
        assert join_name("ns", "*") == "ns/*"
