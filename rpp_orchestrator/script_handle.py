from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
import json
import re
import typing
from typing import Any

if typing.TYPE_CHECKING:
    from .workspace import Workspace

from .utils import import_python_module_from_path


DEFAULT_SCRIPT_CLASS_NAME = "WorkspaceOrchestrationScript"
DEFAULT_SCRIPT_LANGUAGE = "python"

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
    "cpp": ScriptLanguageSpec(name="cpp", extension=".cpp"),
    "hpp": ScriptLanguageSpec(name="cpp", extension=".hpp"),
    "c": ScriptLanguageSpec(name="cpp", extension=".c"),
    "h": ScriptLanguageSpec(name="cpp", extension=".h"),
}

def get_script_language_from_path(script_path: Path) -> str:
    extension = script_path.suffix
    return next((spec.name for spec in SCRIPT_LANGUAGES.values() if spec.extension == extension), DEFAULT_SCRIPT_LANGUAGE)

def language_spec(language: str) -> ScriptLanguageSpec:
    spec = SCRIPT_LANGUAGES.get(language)
    if spec is None:
        raise ValueError(f"Unsupported script language: {language}")
    return spec


class ScriptHandle:
    def __init__(self, path: Path, ws: 'Workspace', language: str | None = None) -> None:

        self.path = path
        if language is None:
            language = get_script_language_from_path(path)
        self.language = language
        self.ws = ws
        self.script_name = path.stem

        self.slots = self._get_script_slots()
        self.description_path = self.ws.get_script_description_path(self.path)
        if not self.description_path.exists():
            self.ws.write_script_description(self.path, self.language, {})

    def add_component_slot(self, slot_name: str, plugin_type: str) -> None:
        self.slots[slot_name] = plugin_type
        if self.language == "python":
            self._save_script_with_slots_python()

    def remove_component_slot(self, slot_name: str) -> None:
        if slot_name in self.slots:
            del self.slots[slot_name]
        if self.language == "python":
            self._save_script_with_slots_python()

    def assign_component_to_slot(self, slot_name: str, record_id: str) -> None:
        """Add a component slot to the script's COMPONENTS dict."""
        description = self.ws.read_script_description(self.path)
        record = self.ws.get_part_record_by_id(record_id)
        description["Components"][slot_name] = {"PluginType": record.plugin_type, "Components": []}
        self.ws.write_script_description(self.path, description)

    def remove_component_from_slot(self, slot_name: str) -> None:
        """Remove a component slot from the script's COMPONENTS dict."""
        description = self.ws.read_script_description(self.path)
        if slot_name not in description["Components"]:
            raise ValueError(f"Component slot '{slot_name}' does not exist in script.")
        del description["Components"][slot_name]
        self.ws.write_script_description(self.path, description)


    def load_description(self) -> dict[str, list[str]]:
        return self.ws.read_script_description(self.path)

    def _load_class_python(self) -> Any:
        module = import_python_module_from_path(self.path.stem, self.path)
        class_name = script_class_name_from_name(self.path.stem)
        if not hasattr(module, class_name):
            raise ValueError(f"Class '{class_name}' not found in script '{self.path}'.")
        return getattr(module, class_name)

    def _strip_new_lines_spaces_and_trailing_commas(self, s: str) -> str:
        return re.sub(r'[\n\s]+', '', s).rstrip(',')

    def _save_script_with_slots_python(self) -> None:
        """Update the script source with the current COMPONENTS dict."""
        source = self.path.read_text(encoding="utf-8")
        components_str = json.dumps(self.slots, indent=4)
        components_str = self._strip_new_lines_spaces_and_trailing_commas(components_str)
        # find the COMPONENTS assignment in the source and replace it
        pattern = r'COMPONENTS\s*=\s*\{.*?\}'
        match = re.search(pattern, source, re.DOTALL)
        if match:
            new_source = re.sub(pattern, f'COMPONENTS = {components_str}', source, re.DOTALL)
            self.path.write_text(new_source, encoding="utf-8")
        else:
            # find the class definition with script name and insert the COMPONENTS assignment after it
            class_pattern = rf'class\s+{script_class_name_from_name(self.path.stem)}(?:\s*\(.*?\))?\s*:'
            match = re.search(class_pattern, source)
            if match:
                insert_pos = match.end()
                new_source = source[:insert_pos] + f'\n    COMPONENTS = {components_str}\n' + source[insert_pos:]
                self.path.write_text(new_source, encoding="utf-8")
            else:
                raise ValueError(f"Class '{script_class_name_from_name(self.path.stem)}' not found in script '{self.path}'.")

    def _parse_cpp_source_for_slots(self) -> dict[str, str]:
        """Parse the script source to extract the RPP_COMPONENTS dict."""
        source = self.path.read_text(encoding="utf-8")
        pattetn = r"RPP_COMPONENTS\s*\(\s*(.*?)\s*\)"
        match = re.search(pattetn, source, re.DOTALL)
        if match:
            content = match.group(1)
            pair_pattern = r'\{\s*"([^"]+)"\s*,\s*"([^"]+)"\s*\}'
            components = dict(re.findall(pair_pattern, content))
            return components
        return {}

    def _get_script_slots(self) -> dict[str, str]:
        if self.language == "python":
            class_obj = self._load_class_python()
            return class_obj.COMPONENTS if hasattr(class_obj, "COMPONENTS") else {}
        elif self.language in ["cpp", "c", "hpp", "h"]:
            return self._parse_cpp_source_for_slots()
        raise ValueError(f"Unsupported script language: {self.language}")

def default_script_source(script_path: Path) -> str:
    class_name = script_class_name_from_name(script_path.stem)
    language = get_script_language_from_path(script_path)
    if language == "python":
        return _python_default_script_source(class_name)
    elif language == "cpp":
        return _cpp_default_script_source(class_name)
    raise ValueError(f"Unsupported script language: {language}")

def _python_default_script_source(class_name: str) -> str:
    return (
        "from __future__ import annotations\n\n"
        f"class {class_name}:\n"
        "    COMPONENTS = {}\n\n"
        ""
        "    def run(self) -> None:\n"
        "        raise NotImplementedError(\"Define the workspace logic here.\")\n"
    )

def _cpp_default_script_source(class_name: str) -> str:
    return (
        "#include <rpp_cpp/plugin.hpp>\n\n"
        "namespace rpp {\n\n"
        f"class {class_name}{{\n"
        "public:\n"
        "    void run() override {\n"
        "        throw std::runtime_error(\"Define the workspace logic here.\");\n"
        "    }\n"
        "};\n\n"
        "} // namespace rpp\n"
    )