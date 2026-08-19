from __future__ import annotations

from rpp_orchestrator.orchestration_script import OrchestrationScript


COMPONENTS = {
    "ctl_main": "rpp_testing::MotionController2D",
    "ctl_disturbance": "rpp_testing::DisturbanceGenerator2D",
}

class MockWorkspace(OrchestrationScript):
    def run(self) -> None:
        raise NotImplementedError("Define the workspace logic here.")
