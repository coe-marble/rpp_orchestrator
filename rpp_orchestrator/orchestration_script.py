from typing import Any
from pathlib import Path
from abc import ABC, abstractmethod


class OrchestrationScript(ABC):

    components = []

    @abstractmethod
    def run(self) -> None:
        raise NotImplementedError


    def get_component(self, slot_name: str) -> Any:
        """Retrieve the component assigned to the given slot name."""
        if slot_name not in self.components:
            raise ValueError(f"Component slot '{slot_name}' does not exist.")
        return self.components[slot_name]