from __future__ import annotations

from rpp_orchestrator.orchestration_script import OrchestrationScript

COMPONENTS = {}

class EmptyWorkspace(OrchestrationScript):
    def run(self) -> None:
        raise NotImplementedError("Define the workspace logic here.")
