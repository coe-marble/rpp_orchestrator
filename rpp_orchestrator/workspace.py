from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
import json
import re
from uuid import uuid4
from typing import Any

from .component_storage import ComponentDataStore, ComponentParameterStore, ComponentRecord


DEFAULT_SCRIPT_CLASS_NAME = "WorkspaceOrchestrationScript"
DEFAULT_SCRIPT_LANGUAGE = "python"
COMPONENTS_START = "# RPP_COMPONENTS_START"
COMPONENTS_END = "# RPP_COMPONENTS_END"


@dataclass(frozen=True)
class ScriptLanguageSpec:
    name: str
    extension: str


SCRIPT_LANGUAGES: dict[str, ScriptLanguageSpec] = {
    "python": ScriptLanguageSpec(name="python", extension=".py"),
}


def script_class_name_from_name(name: str) -> str:
    parts = re.split(r"[^0-9A-Za-z]+", name)
    class_name = "".join(part.capitalize() for part in parts if part)
    return class_name or DEFAULT_SCRIPT_CLASS_NAME


def default_components() -> dict[str, Any]:
    return {"components": {}}


def _part_type_from_descriptor(descriptor: dict[str, Any]) -> str:
    plugin_type = str(descriptor.get("PluginType") or "").strip()
    if "::" in plugin_type:
        return plugin_type.split("::", 1)[1].strip().lower() or "part"
    return plugin_type.lower() or "part"


@dataclass(frozen=True)
class PartRecord:
    script_name: str
    component_key: str
    component_type: str
    folder: Path
    descriptor_path: Path
    descriptor: dict[str, Any]


def _json_load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _json_write(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=4, sort_keys=False), encoding="utf-8")


def _components_block(components: dict[str, Any]) -> str:
    json_text = json.dumps(components, indent=2, sort_keys=True)
    return (
        f"{COMPONENTS_START}\n"
        "COMPONENTS_JSON = r'''\n"
        f"{json_text}\n"
        "'''\n"
        f"{COMPONENTS_END}"
    )


def _python_default_script_source(class_name: str) -> str:
    return (
        "from __future__ import annotations\n\n"
        "from rpp_orchestrator.workspace import OrchestrationScript\n\n"
        "COMPONENTS = {}\n\n"
        f"class {class_name}(OrchestrationScript):\n"
        "    def run(self) -> None:\n"
        "        raise NotImplementedError(\"Define the workspace logic here.\")\n"
    )


def default_script_source(class_name: str = DEFAULT_SCRIPT_CLASS_NAME, language: str = DEFAULT_SCRIPT_LANGUAGE) -> str:
    spec = _language_spec(language)
    if spec.name == "python":
        return _python_default_script_source(class_name)
    raise ValueError(f"Unsupported script language: {language}")


class OrchestrationScript(ABC):

    components = []

    @abstractmethod
    def run(self) -> None:
        raise NotImplementedError


def _language_spec(language: str) -> ScriptLanguageSpec:
    spec = SCRIPT_LANGUAGES.get(language)
    if spec is None:
        raise ValueError(f"Unsupported script language: {language}")
    return spec


def _components_json_pattern() -> re.Pattern[str]:
    return re.compile(
        rf"{re.escape(COMPONENTS_START)}\n"
        r"COMPONENTS_JSON = r'''\n"
        r"(.*?)"
        r"\n'''\n"
        rf"{re.escape(COMPONENTS_END)}",
        re.DOTALL,
    )


@dataclass
class Workspace:
    root: Path
    script_dir_name: str = "scripts"
    parts_dir_name: str = "parts"
    data_dir_name: str = "data"
    builds_dir_name: str = "builds"
    logs_dir_name: str = "logs"
    default_script_language: str = DEFAULT_SCRIPT_LANGUAGE

    @property
    def component_data_store(self) -> ComponentDataStore:
        return ComponentDataStore(self.parts_path)

    @property
    def component_parameter_store(self) -> ComponentParameterStore:
        return self.component_data_store.parameters

    @property
    def name(self) -> str:
        return self.root.name

    @property
    def scripts_path(self) -> Path:
        return self.root / self.script_dir_name

    @property
    def parts_path(self) -> Path:
        return self.root / self.parts_dir_name

    @property
    def data_path(self) -> Path:
        return self.root / self.data_dir_name

    @property
    def builds_path(self) -> Path:
        return self.root / self.builds_dir_name

    @property
    def logs_path(self) -> Path:
        return self.root / self.logs_dir_name

    def write_script(self, script_name: str, source: str, filename: str | None = None, language: str = DEFAULT_SCRIPT_LANGUAGE) -> Path:
        self.scripts_path.mkdir(parents=True, exist_ok=True)
        extension = _language_spec(language).extension
        target = self.scripts_path / (filename or f"{script_name}{extension}")
        target.write_text(source, encoding="utf-8")
        return target

    def ensure_layout(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.scripts_path.mkdir(parents=True, exist_ok=True)
        self.parts_path.mkdir(parents=True, exist_ok=True)
        self.data_path.mkdir(parents=True, exist_ok=True)
        self.builds_path.mkdir(parents=True, exist_ok=True)
        self.logs_path.mkdir(parents=True, exist_ok=True)

    def ensure_parts_layout(self) -> None:
        self.parts_path.mkdir(parents=True, exist_ok=True)

    def list_scripts(self) -> list[Path]:
        self.scripts_path.mkdir(parents=True, exist_ok=True)
        extensions = {spec.extension for spec in SCRIPT_LANGUAGES.values()}
        return sorted(path for path in self.scripts_path.iterdir() if path.is_file() and path.suffix in extensions)

    def create_script(self, script_name: str, source: str | None = None, language: str = DEFAULT_SCRIPT_LANGUAGE) -> Path:
        self.scripts_path.mkdir(parents=True, exist_ok=True)
        extension = _language_spec(language).extension
        target = self.scripts_path / f"{script_name}{extension}"
        target.write_text(source or default_script_source(script_class_name_from_name(script_name), language=language), encoding="utf-8")
        return target

    def delete_script(self, script_path: Path) -> None:
        if script_path.exists():
            script_path.unlink()

    def create_part_folder(
        self,
        descriptor: dict[str, Any],
        *,
        script_name: str | None = None,
        component_key: str | None = None,
        overwrite: bool = False,
    ) -> Path:
        self.ensure_parts_layout()
        descriptor = dict(descriptor)
        component_key = component_key or str(descriptor.get("ComponentKey") or _part_type_from_descriptor(descriptor))
        script_name = script_name or str(descriptor.get("ScriptName") or self.name)
        descriptor.setdefault("ComponentKey", component_key)
        descriptor.setdefault("ScriptName", script_name)
        descriptor.setdefault("Id", str(uuid4()))

        folder = self.component_data_store.create_component_folder(script_name, component_key, descriptor, overwrite=overwrite)
        self.component_data_store.ensure_component_slots(folder, [str(slot) for slot in descriptor.get("Subcomponents", []) if str(slot).strip()])
        return folder

    def create_subcomponent_folder(
        self,
        parent_folder: Path,
        slot_name: str,
        descriptor: dict[str, Any],
        *,
        overwrite: bool = False,
    ) -> Path:
        folder = self.component_data_store.create_subcomponent_folder(parent_folder, slot_name, descriptor, overwrite=overwrite)
        self.component_data_store.ensure_component_slots(folder, [str(slot) for slot in descriptor.get("Subcomponents", []) if str(slot).strip()])
        return folder

    def read_part_descriptor(self, folder: Path) -> dict[str, Any]:
        return self.component_data_store.load_description(folder)

    def write_part_descriptor(self, folder: Path, descriptor: dict[str, Any]) -> Path:
        return self.component_data_store.save_description(folder, descriptor)

    def part_descriptor_path(self, folder: Path) -> Path:
        description_path = folder / "description.json"
        if description_path.exists():
            return description_path
        raise FileNotFoundError(f"No part descriptor JSON found in: {folder}")

    def part_parameters_path(self, folder: Path) -> Path:
        return self.component_parameter_store.parameters_path(folder)

    def list_part_records(self) -> list[PartRecord]:
        self.ensure_parts_layout()
        records: list[PartRecord] = []
        for descriptor_path in self.component_data_store.iter_component_description_files():
            if descriptor_path.name != "description.json":
                continue
            try:
                component_record = self.component_data_store.load_record(descriptor_path)
            except (json.JSONDecodeError, ValueError):
                continue
            records.append(
                PartRecord(
                    script_name=component_record.script_name,
                    component_key=component_record.component_key,
                    component_type=component_record.component_type,
                    folder=component_record.folder,
                    descriptor_path=component_record.descriptor_path,
                    descriptor=component_record.descriptor,
                )
            )
        return records

    def find_part_record_by_id(self, part_id: str) -> PartRecord | None:
        for record in self.list_part_records():
            if str(record.descriptor.get("Id")) == part_id:
                return record
        return None

    def rename_script(self, script_path: Path, new_name: str, language: str | None = None) -> Path:
        ext = _language_spec(language or self.default_script_language).extension if language else script_path.suffix
        target = script_path.with_name(f"{new_name}{ext}")
        if target.exists():
            raise FileExistsError(f"Target script already exists: {target}")
        script_path.rename(target)
        return target

    def read_script_components(self, script_path: Path) -> dict[str, Any]:
        text = script_path.read_text(encoding="utf-8")
        match = _components_json_pattern().search(text)
        if match is None:
            return default_components()
        return json.loads(match.group(1))

    def write_script_components(self, script_path: Path, components: dict[str, Any]) -> None:
        text = script_path.read_text(encoding="utf-8")
        replacement = _components_block(components)
        pattern = _components_json_pattern()
        if pattern.search(text):
            updated = pattern.sub(replacement, text, count=1)
        else:
            updated = f"{text.rstrip()}\n\n{replacement}\n"
        script_path.write_text(updated, encoding="utf-8")

    def write_context(self, name: str, source: str, filename: str | None = None) -> Path:
        target = self.root / (filename or name)
        target.write_text(source, encoding="utf-8")
        return target


def create_workspace(root: str | Path, name: str | None = None, overwrite: bool = False) -> Workspace:
    root_path = Path(root).expanduser().resolve()
    if root_path.exists() and any(root_path.iterdir()) and not overwrite:
        raise FileExistsError(f"Workspace root already exists and is not empty: {root_path}")

    root_path.mkdir(parents=True, exist_ok=True)
    workspace = Workspace(root=root_path)
    workspace.ensure_layout()
    default_script_name = name or workspace.name
    extension = _language_spec(workspace.default_script_language).extension
    default_script = workspace.scripts_path / f"{default_script_name}{extension}"
    if not default_script.exists():
        workspace.create_script(
            default_script_name,
            default_script_source(script_class_name_from_name(default_script_name), language=workspace.default_script_language),
            language=workspace.default_script_language,
        )
    return workspace
