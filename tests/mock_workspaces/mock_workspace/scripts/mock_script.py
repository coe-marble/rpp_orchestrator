from __future__ import annotations

from rpp_orchestrator.workspace import OrchestrationScript
from rpp_common.common_plugins import Controller, Estimator

COMPONENTS = {
    "ctl_main": Controller,
    "est_main": Estimator,
}


class MockScript(OrchestrationScript):
    components = COMPONENTS

    def run(self) -> None:
        raise NotImplementedError
