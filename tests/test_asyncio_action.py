"""Tests for ``zros2.asyncio.AsyncRobotClient.invoke_action``."""

import asyncio
import threading
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest

from zros2 import GoalHandle
from zros2.asyncio import ActionFeedback, ActionResult, AsyncRobotClient
from zros2.asyncio._action import _FEEDBACK_QUEUE_MAX
from zros2.exceptions import ActionInvokeException
from zros2.types import RosAction


class _FakeActionType:
    """Placeholder action type — ``Action`` is mocked away."""


class _ResultResponse:
    """Fake ``GetResult_Response`` carrying status + result payload."""

    def __init__(self, status: int, result: Any) -> None:
        self.status = status
        self.result = result


class _FeedbackMessage:
    """Fake ``FeedbackMessage`` wrapping a feedback payload."""

    def __init__(self, feedback: Any) -> None:
        self.feedback = feedback


def _mock_action() -> type[RosAction[Any, Any, Any, Any, Any, Any, Any, Any]]:
    """Return the placeholder action type cast to the RosAction protocol."""
    return cast(
        type[RosAction[Any, Any, Any, Any, Any, Any, Any, Any]], _FakeActionType
    )


def _make_fake_action(
    *,
    accepted: bool = True,
    result: Any = None,
    result_gate: threading.Event | None = None,
) -> MagicMock:
    """Build a fake ``Action`` with scripted send-goal / get-result responses."""
    fake_action = MagicMock()
    fake_action.__enter__.return_value = fake_action
    fake_action.send_goal.return_value = GoalHandle(
        goal_id=tuple(range(16)), accepted=accepted
    )
    if result_gate is None:
        fake_action.get_result.return_value = _ResultResponse(4, result)
    else:

        def _wait_for_gate(
            handle: GoalHandle, timeout: int | None = None
        ) -> _ResultResponse:
            result_gate.wait()
            return _ResultResponse(4, result)

        fake_action.get_result.side_effect = _wait_for_gate
    return fake_action


class TestAsyncRobotClientAction:
    """``invoke_action`` over the threaded ``Action`` endpoint."""

    @pytest.mark.asyncio
    async def test_yields_feedback_then_result(self):
        """Feedback and the final result should arrive in order."""
        feedback = object()
        result = object()
        result_gate = threading.Event()
        fake_action = _make_fake_action(result=result, result_gate=result_gate)

        async def _pump_feedback() -> None:
            await asyncio.sleep(0)
            fake_action.feedback_callback(_FeedbackMessage(feedback))

        with patch("zros2.asyncio._action.Action") as action_cls:
            action_cls.return_value = fake_action
            pump = asyncio.create_task(_pump_feedback())
            collected: list[Any] = []
            async for event in AsyncRobotClient(MagicMock()).invoke_action(
                "test/action", _mock_action()
            ):
                collected.append(event)
                if isinstance(event, ActionFeedback):
                    result_gate.set()
            await pump

        assert len(collected) == 2
        assert isinstance(collected[0], ActionFeedback)
        assert collected[0].feedback is feedback
        assert isinstance(collected[1], ActionResult)
        assert collected[1].status == 4
        assert collected[1].result is result

    @pytest.mark.asyncio
    async def test_no_feedback_yields_result_only(self):
        """A result-only invocation should yield exactly one event."""
        result = object()
        with patch("zros2.asyncio._action.Action") as action_cls:
            action_cls.return_value = _make_fake_action(result=result)
            collected = [
                event
                async for event in AsyncRobotClient(MagicMock()).invoke_action(
                    "test/action", _mock_action()
                )
            ]

        assert len(collected) == 1
        assert isinstance(collected[0], ActionResult)
        assert collected[0].result is result

    @pytest.mark.asyncio
    async def test_goal_rejected_raises(self):
        """A rejected goal should raise ActionInvokeException."""
        with patch("zros2.asyncio._action.Action") as action_cls:
            action_cls.return_value = _make_fake_action(accepted=False)

            with pytest.raises(ActionInvokeException):
                async for _ in AsyncRobotClient(MagicMock()).invoke_action(
                    "test/action", _mock_action()
                ):
                    pass

    @pytest.mark.asyncio
    async def test_send_goal_failure_propagates(self):
        """ActionInvokeException from send_goal should propagate."""
        fake_action = _make_fake_action()
        fake_action.send_goal.side_effect = ActionInvokeException("server not ready")
        with patch("zros2.asyncio._action.Action") as action_cls:
            action_cls.return_value = fake_action

            with pytest.raises(ActionInvokeException, match="server not ready"):
                async for _ in AsyncRobotClient(MagicMock()).invoke_action(
                    "test/action", _mock_action()
                ):
                    pass

    @pytest.mark.asyncio
    async def test_get_result_failure_propagates(self):
        """ActionInvokeException from get_result should propagate."""
        fake_action = _make_fake_action()
        fake_action.get_result.side_effect = ActionInvokeException("result lost")
        with patch("zros2.asyncio._action.Action") as action_cls:
            action_cls.return_value = fake_action

            with pytest.raises(ActionInvokeException, match="result lost"):
                async for _ in AsyncRobotClient(MagicMock()).invoke_action(
                    "test/action", _mock_action()
                ):
                    pass

    @pytest.mark.asyncio
    async def test_forwards_goal_timeout_and_namespace(self):
        """Arguments should reach the endpoint construction and the calls."""
        goal = object()
        fake_proxy = MagicMock()
        with patch("zros2.asyncio._action.Action") as action_cls:
            action_cls.return_value = _make_fake_action()

            async for _ in AsyncRobotClient(fake_proxy).invoke_action(
                "test/action",
                _mock_action(),
                goal=goal,
                timeout=5000,
                namespace="robot_01",
            ):
                pass

        action_cls.assert_called_once_with(
            fake_proxy, "robot_01/test/action", _mock_action(), 5000
        )
        fake_action = action_cls.return_value
        fake_action.send_goal.assert_called_once_with(goal)
        fake_action.get_result.assert_called_once_with(
            fake_action.send_goal.return_value, 5000
        )

    @pytest.mark.asyncio
    async def test_none_timeout_defaults_to_3000(self):
        """A None timeout should default to 3000 for the endpoint only."""
        fake_proxy = MagicMock()
        with patch("zros2.asyncio._action.Action") as action_cls:
            action_cls.return_value = _make_fake_action()

            async for _ in AsyncRobotClient(fake_proxy).invoke_action(
                "test/action", _mock_action()
            ):
                pass

        action_cls.assert_called_once_with(
            fake_proxy, "test/action", _mock_action(), 3000
        )
        fake_action = action_cls.return_value
        fake_action.get_result.assert_called_once_with(
            fake_action.send_goal.return_value, None
        )

    @pytest.mark.asyncio
    async def test_early_exit_is_clean(self):
        """Breaking out of the async-for should cancel pending tasks."""
        result_gate = threading.Event()
        fake_action = _make_fake_action(result=object(), result_gate=result_gate)

        async def _pump_feedback() -> None:
            await asyncio.sleep(0)
            fake_action.feedback_callback(_FeedbackMessage(object()))

        with patch("zros2.asyncio._action.Action") as action_cls:
            action_cls.return_value = fake_action
            pump = asyncio.create_task(_pump_feedback())
            generator = AsyncRobotClient(MagicMock()).invoke_action(
                "test/action", _mock_action()
            )
            async for _ in generator:
                break
            result_gate.set()  # release the get_result worker before the loop closes
            await generator.aclose()
            await pump

    @pytest.mark.asyncio
    async def test_feedback_queue_is_bounded(self):
        """Feedback beyond the queue capacity should be dropped, not raise."""
        result_gate = threading.Event()
        fake_action = _make_fake_action(result=object(), result_gate=result_gate)

        async def _pump_feedback() -> None:
            await asyncio.sleep(0)
            for _ in range(_FEEDBACK_QUEUE_MAX * 2):
                fake_action.feedback_callback(_FeedbackMessage(object()))

        with patch("zros2.asyncio._action.Action") as action_cls:
            action_cls.return_value = fake_action
            pump = asyncio.create_task(_pump_feedback())
            feedback_count = 0
            result_seen = False
            async for event in AsyncRobotClient(MagicMock()).invoke_action(
                "test/action", _mock_action()
            ):
                if isinstance(event, ActionFeedback):
                    feedback_count += 1
                    if feedback_count == _FEEDBACK_QUEUE_MAX:
                        result_gate.set()
                else:
                    result_seen = True
            await pump

        assert feedback_count == _FEEDBACK_QUEUE_MAX
        assert result_seen
