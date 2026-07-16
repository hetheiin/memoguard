from __future__ import annotations

from enum import Enum


class ActionType(str, Enum):
    FOLLOW_PLANNER = "follow_planner"
    INSPECT_TARGET = "inspect_target"
    RETURN_TO_SAFE_WAYPOINT = "return_to_safe_waypoint"
    INSPECT_ALTERNATE_VIEWPOINT = "inspect_alternate_viewpoint"
    WAIT_FOR_RECOVERY = "wait_for_recovery"
    ABORT_MISSION = "abort_mission"
