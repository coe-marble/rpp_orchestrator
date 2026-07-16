
from __future__ import annotations

from rpp_orchestrator.orchestration_script import OrchestrationScript

from rpp_plugin_types.rpp_common import MotionController2D
from rpp_plugin_types.rpp_common import DisturbanceGenerator2D


COMPONENTS = {
    "ctl_main": "rpp_common::MotionController2D",
    "ctl_disturbance": "rpp_common::DisturbanceGenerator2D",
}

class MockWorkspace(OrchestrationScript):
    def run(self) -> None:
        raise NotImplementedError("Define the workspace logic here.")
