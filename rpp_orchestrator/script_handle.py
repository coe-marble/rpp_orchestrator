from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
import json5
import re
import typing
from typing import Any

if typing.TYPE_CHECKING:
    from .workspace import Workspace


DEFAULT_SCRIPT_CLASS_NAME = "WorkspaceOrchestrationScript"
DEFAULT_SCRIPT_LANGUAGE = "python"
COMPONENTS_START = "# RPP_COMPONENTS_START"
COMPONENTS_END = "# RPP_COMPONENTS_END"

def script_class_name_from_name(name: str) -> str:
    parts = re.split(r"[^0-9A-Za-z]+", name)
    class_name = "".join(part.capitalize() for part in parts if part)
    return class_name or DEFAULT_SCRIPT_CLASS_NAME

@dataclass(frozen=True)
class ScriptLanguageSpec:
    name: str
    extension: str


SCRIPT_LANGUAGES: dict[str, ScriptLanguageSpec] = {
    "python": ScriptLanguageSpec(name="python", extension=".py"),
}

def language_spec(language: str) -> ScriptLanguageSpec:
    spec = SCRIPT_LANGUAGES.get(language)
    if spec is None:
        raise ValueError(f"Unsupported script language: {language}")
    return spec


class ScriptHandle:
    def __init__(self, path: Path, ws: 'Workspace', language: str | None = None) -> None:

        self.path = path
        self.source = path.read_text(encoding="utf-8")
        if language is None:
            extension = path.suffix
            language = next((spec.name for spec in SCRIPT_LANGUAGES.values() \
                             if spec.extension == extension), None)
        self.language = language
        self.ws = ws
        self.slots = self._parse_component_slots()

    def add_component_slot(self, slot_name: str, plugin_type: str) -> None:
        self.slots[slot_name] = plugin_type
        self._save_script_with_slots()

    def remove_component_slot(self, slot_name: str) -> None:
        if slot_name in self.slots:
            del self.slots[slot_name]
            self._save_script_with_slots()

    def assign_component_to_slot(self, slot_name: str, record_id: str) -> None:
        """Add a component slot to the script's COMPONENTS dict."""
        components = self.ws.read_script_component_assignments(self.path)
        components[slot_name] = {"plugin_type": plugin_type, "components": []}
        self.ws.write_script_component_assignments(self.path, components)

    def remove_component_from_slot(self, slot_name: str) -> None:
        """Remove a component slot from the script's COMPONENTS dict."""
        components = self.ws.read_script_component_assignments(self.path)
        if slot_name not in components:
            raise ValueError(f"Component slot '{slot_name}' does not exist in script.")
        del components[slot_name]
        self.ws.write_script_component_assignments(self.path, components)


    def load_assignments(self) -> dict[str, list[str]]:
        return self.ws.read_script_component_assignments(self.path)

    def _parse_component_slots(self) -> dict[str, str]:

        regex = re.compile(r'COMPONENTS\s*=\s*{(.*?)}', re.DOTALL)
        match = regex.search(self.source)
        if not match:
            raise ValueError("COMPONENTS dictionary not found in script source.")
        components_str = self._strip_new_lines_spaces_and_trailing_commas(match.group(1))
        slots = {}
        try:
            slots = json5.loads(f"{{{components_str}}}")
        except ValueError as e:
            self.slots = {}
        return slots

    def _strip_new_lines_spaces_and_trailing_commas(self, s: str) -> str:
        return re.sub(r'[\n\s]+', '', s).rstrip(',')

    def _save_script_with_slots(self) -> None:
        """Update the script source with the current COMPONENTS dict."""
        components_str = ",\n    ".join(
            f'"{slot}": "{ptype}"' for slot, ptype in self.slots.items()
        )
        new_source = re.sub(
            r'COMPONENTS\s*=\s*{.*?}',
            f'COMPONENTS = {{\n    {components_str}\n}}',
            self.source,
            flags=re.DOTALL
        )
        self.source = new_source
        self.path.write_text(new_source, encoding="utf-8")

def default_script_source(class_name: str = DEFAULT_SCRIPT_CLASS_NAME, language: str = DEFAULT_SCRIPT_LANGUAGE) -> str:
    spec = language_spec(language)
    if spec.name == "python":
        return _python_default_script_source(class_name)
    raise ValueError(f"Unsupported script language: {language}")

def _python_default_script_source(class_name: str) -> str:
    return (
        "from __future__ import annotations\n\n"
        "from rpp_orchestrator.orchestration_script import OrchestrationScript\n\n"
        "COMPONENTS = {}\n\n"
        f"class {class_name}(OrchestrationScript):\n"
        "    def run(self) -> None:\n"
        "        raise NotImplementedError(\"Define the workspace logic here.\")\n"
    )