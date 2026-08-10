"""Unit tests for :class:`zros2.endpoints.Action` edge cases."""

from typing import Any, cast
from unittest.mock import MagicMock

import pytest

from zros2.endpoints import Action, GoalHandle
from zros2.exceptions import ActionInvokeException
from zros2.types import RosAction


class _MockActionType:
    """Minimal action type satisfying the RosAction protocol."""

    class Goal:
        def serialize(self) -> bytes:
            return b""

    class Result:
        pass

    class Feedback:
        pass

    class FeedbackMessage:
        @classmethod
        def deserialize(cls, data: bytes):
            return cls()

    class SendGoal_Request:
        def serialize(self) -> bytes:
            return b""

    class SendGoal_Response:
        """Response with the ``accepted`` flag set by the server."""

        accepted = True

        @classmethod
        def deserialize(cls, data: bytes):
            return cls()

    class GetResult_Request:
        def serialize(self) -> bytes:
            return b""

    class GetResult_Response:
        @classmethod
        def deserialize(cls, data: bytes):
            return cls()


_mock_action: type[RosAction[Any, Any, Any, Any, Any, Any, Any, Any]] = cast(
    type[RosAction[Any, Any, Any, Any, Any, Any, Any, Any]], _MockActionType
)


class TestAction:
    """Tests for Action that don't need a real Zenoh session."""

    def test_init_creates_feedback_subscriber(self):
        """Constructor should set up the feedback subscriber."""
        session = MagicMock()
        action = Action(session, "test/action", _mock_action, timeout=3000)
        assert action._action_name == "test/action"
        assert action._timeout == 3000
        assert action._feedback_subscriber is not None

    def test_new_goal_id_returns_16_bytes(self):
        """_new_goal_id should return 16 random bytes."""
        goal_id = Action._new_goal_id()
        assert isinstance(goal_id, bytes)
        assert len(goal_id) == 16

    def test_new_goal_id_is_random(self):
        """Two calls to _new_goal_id should return different values."""
        id1 = Action._new_goal_id()
        id2 = Action._new_goal_id()
        assert id1 != id2

    def test_make_srv_type_is_cached(self):
        """_make_srv_type should reuse the class for identical inputs."""
        from typing import cast

        from zros2.endpoints._action import _make_srv_type
        from zros2.types import RosMessage

        request = cast(type[RosMessage], _MockActionType.SendGoal_Request)
        response = cast(type[RosMessage], _MockActionType.SendGoal_Response)
        first = _make_srv_type("_X", request, response)
        second = _make_srv_type("_X", request, response)
        assert first is second
        assert first.Request is _MockActionType.SendGoal_Request
        assert first.Response is _MockActionType.SendGoal_Response

    def test_context_manager(self):
        """Entering and exiting the context manager should not raise."""
        session = MagicMock()
        action = Action(session, "test/action", _mock_action, timeout=3000)
        with action as act:
            assert act is action
        # __exit__ calls unsubscribe on the feedback subscriber
        assert action._feedback_subscriber._subscriber is None

    def test_feedback_callback_setter_and_getter(self):
        """Setting and getting the feedback callback should work."""
        session = MagicMock()
        action = Action(session, "test/action", _mock_action, timeout=3000)

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

        action = Action(session, "test/action", _mock_action, timeout=3000)
        with pytest.raises(ActionInvokeException):
            action.send_goal()

    def test_send_goal_with_feedback_callback(self):
        """send_goal should subscribe feedback when callback is set.

        Covers the ``if (callback := self._feedback_callback) is not None:`` branch.
        """
        session = MagicMock()
        session.is_closed.return_value = False
        session.get.return_value = iter([])

        action = Action(session, "test/action", _mock_action, timeout=3000)
        action.feedback_callback = lambda msg: None
        with pytest.raises(ActionInvokeException):
            action.send_goal()
        # feedback_subscriber.subscribe was called
        assert action._feedback_subscriber._subscriber is not None

    def test_send_goal_with_explicit_goal(self):
        """send_goal with an explicit goal argument should use it.

        Covers the ``if goal is None:`` branch where goal is provided.
        """
        session = MagicMock()
        session.is_closed.return_value = False
        session.get.return_value = iter([])

        action = Action(session, "test/action", _mock_action, timeout=3000)
        goal = _MockActionType.Goal()
        with pytest.raises(ActionInvokeException):
            action.send_goal(goal=goal)

    def test_get_result_raises_action_invoke_exception(self):
        """get_result should wrap ServiceException in ActionInvokeException."""
        session = MagicMock()
        session.is_closed.return_value = False
        session.get.return_value = iter([])

        action = Action(session, "test/action", _mock_action, timeout=3000)
        handle = GoalHandle(goal_id=tuple(range(16)), accepted=True)
        with pytest.raises(ActionInvokeException):
            action.get_result(handle)

    def test_get_result_requires_goal_handle(self):
        """get_result without a handle should fail fast (TypeError)."""
        session = MagicMock()
        action = Action(session, "test/action", _mock_action, timeout=3000)
        with pytest.raises(TypeError):
            action.get_result()  # type: ignore[call-arg]

    def test_send_goal_twice_returns_unique_handles(self):
        """Each send_goal gets a fresh goal ID; reuse must not raise."""
        session = MagicMock()
        session.is_closed.return_value = False
        reply = MagicMock()
        reply.ok.payload = b""
        session.get.side_effect = lambda *args, **kwargs: iter([reply])

        action = Action(session, "test/action", _mock_action, timeout=3000)
        action.feedback_callback = lambda msg: None

        first = action.send_goal()
        second = action.send_goal()

        assert isinstance(first, GoalHandle)
        assert first.accepted is True
        assert first.goal_id != second.goal_id
        assert len(first.goal_id) == 16

    def test_send_goal_failure_cleans_up_goal_id(self):
        """A failed send must not leave the goal tracked as active."""
        session = MagicMock()
        session.is_closed.return_value = False
        session.get.return_value = iter([])

        action = Action(session, "test/action", _mock_action, timeout=3000)
        action.feedback_callback = lambda msg: None
        with pytest.raises(ActionInvokeException):
            action.send_goal()
        assert action._active_goal_ids == set()

    def test_feedback_filtered_by_goal_id(self):
        """Only feedback for goals sent through this client is forwarded."""
        session = MagicMock()
        session.is_closed.return_value = False
        reply = MagicMock()
        reply.ok.payload = b""
        session.get.return_value = iter([reply])

        action = Action(session, "test/action", _mock_action, timeout=3000)
        received: list[object] = []
        action.feedback_callback = received.append

        handle = action.send_goal()
        mine = MagicMock()
        mine.goal_id = bytes(handle.goal_id)
        action._forward_feedback(mine)
        assert received == [mine]

        foreign = MagicMock()
        foreign.goal_id = tuple(range(16))
        action._forward_feedback(foreign)
        assert received == [mine]

    def test_cancel_goal_sends_request_with_goal_id(self):
        """cancel_goal should transmit the goal's own ID to the server."""
        from zros2 import CancelGoal_Request, CancelGoal_Response

        session = MagicMock()
        session.is_closed.return_value = False
        reply = MagicMock()
        reply.ok.payload = CancelGoal_Response(return_code=0).serialize()
        session.get.return_value = iter([reply])

        action = Action(session, "test/action", _mock_action, timeout=3000)
        handle = GoalHandle(goal_id=tuple(range(16)), accepted=True)

        response = action.cancel_goal(handle)

        assert response.return_code == CancelGoal_Response.ERROR_NONE
        sent = CancelGoal_Request.deserialize(session.get.call_args.kwargs["payload"])
        assert sent.goal_info.goal_id == bytes(range(16))

    def test_cancel_all_goals_sends_zero_goal_id(self):
        """cancel_all_goals should use the all-zero wildcard goal ID."""
        from zros2 import CancelGoal_Request, CancelGoal_Response

        session = MagicMock()
        session.is_closed.return_value = False
        reply = MagicMock()
        reply.ok.payload = CancelGoal_Response(return_code=0).serialize()
        session.get.return_value = iter([reply])

        action = Action(session, "test/action", _mock_action, timeout=3000)
        response = action.cancel_all_goals()

        assert response.return_code == CancelGoal_Response.ERROR_NONE
        sent = CancelGoal_Request.deserialize(session.get.call_args.kwargs["payload"])
        assert sent.goal_info.goal_id == b"\x00" * 16

    def test_cancel_goal_failure_raises(self):
        """A failed cancel call should raise ActionInvokeException."""
        session = MagicMock()
        session.is_closed.return_value = False
        session.get.return_value = iter([])

        action = Action(session, "test/action", _mock_action, timeout=3000)
        handle = GoalHandle(goal_id=tuple(range(16)), accepted=True)
        with pytest.raises(ActionInvokeException):
            action.cancel_goal(handle)

    def test_status_callback_subscribes_and_forwards(self):
        """Setting a status callback should subscribe and forward updates."""
        session = MagicMock()
        session.is_closed.return_value = False
        action = Action(session, "test/action", _mock_action, timeout=3000)

        received: list[object] = []
        action.status_callback = received.append
        assert action._status_subscriber._subscriber is not None

        status_array = MagicMock()
        action._forward_status(status_array)
        assert received == [status_array]

        action.status_callback = None
        action._forward_status(status_array)
        assert received == [status_array]
