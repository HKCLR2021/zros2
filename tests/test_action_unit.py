"""Unit tests for :class:`zros2._action.Action` edge cases."""

from unittest.mock import MagicMock, patch

import pytest

from zros2._action import Action
from zros2.exceptions import ActionInvokeException


class _MockActionType:
    """Minimal action type satisfying the RosAction protocol."""

    class Goal:
        def serialize(self):
            return b""

    class Result:
        pass

    class Feedback:
        pass

    class FeedbackMessage:
        @classmethod
        def deserialize(cls, data):
            return cls()

    class SendGoal_Request:
        def serialize(self):
            return b""

    class SendGoal_Response:
        @classmethod
        def deserialize(cls, data):
            return cls()

    class GetResult_Request:
        def serialize(self):
            return b""

    class GetResult_Response:
        @classmethod
        def deserialize(cls, data):
            return cls()


class TestAction:
    """Tests for Action that don't need a real Zenoh session."""

    def test_init_creates_feedback_subscriber(self):
        """Constructor should set up the feedback subscriber."""
        session = MagicMock()
        action = Action(session, "test/action", _MockActionType, timeout=3000)
        assert action._action_name == "test/action"
        assert action._timeout == 3000
        assert action._feedback_subscriber is not None

    def test_new_goal_id_returns_16_bytes(self):
        """_new_goal_id should return a list of 16 integers."""
        goal_id = Action._new_goal_id()
        assert isinstance(goal_id, list)
        assert len(goal_id) == 16
        assert all(isinstance(b, int) and 0 <= b <= 255 for b in goal_id)

    def test_new_goal_id_is_random(self):
        """Two calls to _new_goal_id should return different values."""
        id1 = Action._new_goal_id()
        id2 = Action._new_goal_id()
        assert id1 != id2

    def test_context_manager(self):
        """Entering and exiting the context manager should not raise."""
        session = MagicMock()
        action = Action(session, "test/action", _MockActionType, timeout=3000)
        with action as act:
            assert act is action
        # __exit__ calls unsubscribe on the feedback subscriber
        assert action._feedback_subscriber._subscriber is None

    def test_feedback_callback_setter_and_getter(self):
        """Setting and getting the feedback callback should work."""
        session = MagicMock()
        action = Action(session, "test/action", _MockActionType, timeout=3000)

        assert action.feedback_callback is None

        def my_callback(msg):
            pass

        action.feedback_callback = my_callback
        assert action.feedback_callback is my_callback

    def test_send_goal_raises_action_invoke_exception(self):
        """send_goal should wrap ServiceException in ActionInvokeException."""
        session = MagicMock()
        session.is_closed.return_value = False
        # Make get return empty iterator (service unavailable)
        session.get.return_value = iter([])

        action = Action(session, "test/action", _MockActionType, timeout=3000)
        with pytest.raises(ActionInvokeException):
            action.send_goal()

    def test_get_result_raises_action_invoke_exception(self):
        """get_result should wrap ServiceException in ActionInvokeException."""
        session = MagicMock()
        session.is_closed.return_value = False
        session.get.return_value = iter([])

        action = Action(session, "test/action", _MockActionType, timeout=3000)
        with pytest.raises(ActionInvokeException):
            action.get_result()
