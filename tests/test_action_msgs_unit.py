"""Tests for the built-in action protocol message types (zros2._action_msgs)."""

from typing import cast

from zros2 import (
    CancelGoal_Request,
    CancelGoal_Response,
    GoalInfo,
    GoalStatus,
    GoalStatusArray,
    RosMessage,
)


class TestActionMsgs:
    """CDR round-trips and dict conversion for the built-in types."""

    def test_time_is_part_of_goal_info_round_trip(self):
        goal = GoalInfo(goal_id=tuple(range(16)))
        restored = GoalInfo.deserialize(goal.serialize())

        assert restored.goal_id == bytes(range(16))
        assert restored.stamp.sec == 0
        assert restored.stamp.nanosec == 0

    def test_cancel_request_round_trip(self):
        request = CancelGoal_Request(goal_info=GoalInfo(goal_id=tuple(range(16))))
        restored = CancelGoal_Request.deserialize(request.serialize())

        assert restored.goal_info.goal_id == bytes(range(16))

    def test_cancel_response_round_trip(self):
        response = CancelGoal_Response(
            return_code=0,
            goals_canceling=[GoalInfo(goal_id=tuple(range(16)))],
        )
        restored = CancelGoal_Response.deserialize(response.serialize())

        assert restored.return_code == 0
        assert len(cast(list, restored.goals_canceling)) == 1
        assert cast(list, restored.goals_canceling)[0].goal_id == bytes(range(16))

    def test_status_array_round_trip(self):
        status_array = GoalStatusArray(
            status_list=[
                GoalStatus(status=GoalStatus.STATUS_EXECUTING),
                GoalStatus(status=GoalStatus.STATUS_SUCCEEDED),
            ]
        )
        restored = GoalStatusArray.deserialize(status_array.serialize())

        assert [s.status for s in cast(list, restored.status_list)] == [2, 4]

    def test_goal_status_constants(self):
        assert GoalStatus.STATUS_UNKNOWN == 0
        assert GoalStatus.STATUS_ACCEPTED == 1
        assert GoalStatus.STATUS_EXECUTING == 2
        assert GoalStatus.STATUS_CANCELING == 3
        assert GoalStatus.STATUS_SUCCEEDED == 4
        assert GoalStatus.STATUS_CANCELED == 5
        assert GoalStatus.STATUS_ABORTED == 6

    def test_cancel_response_constants(self):
        assert CancelGoal_Response.ERROR_NONE == 0
        assert CancelGoal_Response.ERROR_REJECTED == 1
        assert CancelGoal_Response.ERROR_UNKNOWN_GOAL == 2
        assert CancelGoal_Response.ERROR_GOAL_TERMINATED == 3

    def test_to_dict_from_dict_round_trip(self):
        response = CancelGoal_Response(
            return_code=1,
            goals_canceling=[GoalInfo(goal_id=tuple(range(16)))],
        )
        data = response.to_dict()
        restored = CancelGoal_Response.from_dict(data)

        assert restored.return_code == 1
        # from_dict passes the dict value through, so the array keeps its
        # constructor-side representation (tuple)
        assert cast(list, restored.goals_canceling)[0].goal_id == tuple(range(16))

    def test_structurally_satisfies_ros_message(self):
        instance = GoalStatusArray()
        assert isinstance(instance, RosMessage)
