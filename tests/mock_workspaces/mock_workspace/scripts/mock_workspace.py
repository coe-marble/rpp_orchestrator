from __future__ import annotations

from rpp_orchestrator.workspace import OrchestrationScript

COMPONENTS = {}

class MockWorkspace(OrchestrationScript):
    def run(self) -> None:
        raise NotImplementedError("Define the workspace logic here.")
