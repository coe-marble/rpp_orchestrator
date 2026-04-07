from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4
import json

from .layout import ComponentLayout, default_component_layout


@dataclass(frozen=True)
class ComponentRecord:
    script_name: str
    component_key: str
    component_type: str
    folder: Path
    descriptor_path: Path
    descriptor: dict[str, Any]


class ComponentParameterStore:
    def __init__(self, layout: ComponentLayout | None = None):
        self.layout = layout or default_component_layout()

    def parameters_path(self, component_folder: Path) -> Path:
        return component_folder / self.layout.params_dir / self.layout.parameters_filename

    def load(self, component_folder: Path) -> dict[str, Any]:
        params_path = self.parameters_path(component_folder)
        if not params_path.exists():
            return {}
        return json.loads(params_path.read_text(encoding="utf-8"))

    def save(self, component_folder: Path, payload: dict[str, Any]) -> Path:
        params_path = self.parameters_path(component_folder)
        params_path.parent.mkdir(parents=True, exist_ok=True)
        params_path.write_text(json.dumps(payload, indent=4, sort_keys=False), encoding="utf-8")
        return params_path

    def ensure(self, component_folder: Path) -> Path:
        params_path = self.parameters_path(component_folder)
        params_path.parent.mkdir(parents=True, exist_ok=True)
        if not params_path.exists():
            params_path.write_text("{}\n", encoding="utf-8")
        return params_path


class ComponentDataStore:
    def __init__(self, parts_root: Path, layout: ComponentLayout | None = None):
        self.parts_root = Path(parts_root)
        self.layout = layout or default_component_layout()
        self.parameters = ComponentParameterStore(self.layout)

    def script_root(self, script_name: str) -> Path:
        return self.parts_root / script_name

    def component_options_root(self, script_name: str, component_key: str) -> Path:
        return self.script_root(script_name) / component_key / self.layout.options_dir

    def component_folder(self, script_name: str, component_key: str, component_id: str) -> Path:
        return self.component_options_root(script_name, component_key) / component_id

    def description_path(self, component_folder: Path) -> Path:
        return component_folder / self.layout.description_filename

    def callbacks_path(self, component_folder: Path) -> Path:
        return component_folder / self.layout.callbacks_filename

    def data_path(self, component_folder: Path) -> Path:
        return component_folder / self.layout.data_dir

    def subcomponents_path(self, component_folder: Path) -> Path:
        return component_folder / self.layout.subcomponents_dir

    def save_description(self, component_folder: Path, payload: dict[str, Any]) -> Path:
        payload = self._with_parent_component_id(component_folder, payload)
        description_path = self.description_path(component_folder)
        description_path.parent.mkdir(parents=True, exist_ok=True)
        description_path.write_text(json.dumps(payload, indent=4, sort_keys=False), encoding="utf-8")
        return description_path

    def _with_parent_component_id(self, component_folder: Path, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(payload)
        parent_component_id = self._infer_parent_component_id(component_folder)
        if parent_component_id is not None:
            normalized.setdefault("ParentComponentId", parent_component_id)
        return normalized

    def _infer_parent_component_id(self, component_folder: Path) -> str | None:
        parts = component_folder.parts
        try:
            subcomponents_index = parts.index(self.layout.subcomponents_dir)
        except ValueError:
            return None

        if subcomponents_index == 0:
            return None

        # .../<parent_uuid>/subcomponents/<slot>/options/<component_uuid>
        return parts[subcomponents_index - 1]

    def load_description(self, component_folder: Path) -> dict[str, Any]:
        description_path = self.description_path(component_folder)
        return json.loads(description_path.read_text(encoding="utf-8"))

    def ensure_component_folder(self, component_folder: Path) -> None:
        component_folder.mkdir(parents=True, exist_ok=True)
        self.data_path(component_folder).mkdir(parents=True, exist_ok=True)
        self.subcomponents_path(component_folder).mkdir(parents=True, exist_ok=True)
        self.parameters.ensure(component_folder)
        callbacks_path = self.callbacks_path(component_folder)
        if not callbacks_path.exists():
            callbacks_path.write_text("from __future__ import annotations\n", encoding="utf-8")

    def create_component_folder(
        self,
        script_name: str,
        component_key: str,
        descriptor: dict[str, Any],
        *,
        overwrite: bool = False,
    ) -> Path:
        component_id = str(descriptor.get("Id") or uuid4())
        payload = dict(descriptor)
        payload["Id"] = component_id
        payload.setdefault("ComponentKey", component_key)
        payload.setdefault("ScriptName", script_name)

        folder = self.component_folder(script_name, component_key, component_id)
        if folder.exists() and not overwrite:
            raise FileExistsError(f"Component folder already exists: {folder}")
        folder.mkdir(parents=True, exist_ok=True)

        self.ensure_component_folder(folder)
        self.save_description(folder, payload)
        return folder

    def create_subcomponent_folder(
        self,
        parent_component_folder: Path,
        slot_name: str,
        descriptor: dict[str, Any],
        *,
        overwrite: bool = False,
    ) -> Path:
        parent_descriptor = self.load_description(parent_component_folder)
        parent_component_id = str(parent_descriptor.get("Id") or parent_component_folder.name)

        component_id = str(descriptor.get("Id") or uuid4())
        payload = dict(descriptor)
        payload["Id"] = component_id
        payload.setdefault("ComponentKey", slot_name)
        payload.setdefault("ScriptName", parent_descriptor.get("ScriptName", ""))
        payload.setdefault("ParentComponentId", parent_component_id)

        folder = self.component_slot_options_root(parent_component_folder, slot_name) / component_id
        if folder.exists() and not overwrite:
            raise FileExistsError(f"Component folder already exists: {folder}")

        folder.mkdir(parents=True, exist_ok=True)
        self.ensure_component_folder(folder)
        self.save_description(folder, payload)
        return folder

    def component_slot_options_root(self, component_folder: Path, slot_name: str) -> Path:
        return self.subcomponents_path(component_folder) / slot_name / self.layout.options_dir

    def ensure_component_slots(self, component_folder: Path, slot_names: list[str]) -> None:
        for slot_name in slot_names:
            self.component_slot_options_root(component_folder, slot_name).mkdir(parents=True, exist_ok=True)

    def iter_component_description_files(self) -> list[Path]:
        if not self.parts_root.exists():
            return []
        return sorted(path for path in self.parts_root.glob("**/description.json") if path.is_file())

    def parse_component_location(self, description_path: Path) -> tuple[str, str, Path]:
        relative = description_path.relative_to(self.parts_root)
        parts = relative.parts
        if len(parts) < 5 or description_path.name != self.layout.description_filename or self.layout.options_dir not in parts:
            raise ValueError(f"Invalid component path: {description_path}")

        options_index = len(parts) - 2
        while options_index >= 0 and parts[options_index] != self.layout.options_dir:
            options_index -= 1
        if options_index < 2:
            raise ValueError(f"Invalid component path: {description_path}")

        script_name = parts[0]
        component_key = parts[options_index - 1]
        component_folder = description_path.parent
        return script_name, component_key, component_folder

    def load_record(self, description_path: Path) -> ComponentRecord:
        script_name, component_key, component_folder = self.parse_component_location(description_path)
        descriptor = json.loads(description_path.read_text(encoding="utf-8"))
        plugin_type = str(descriptor.get("PluginType") or "").strip()
        if "::" in plugin_type:
            component_type = plugin_type.split("::", 1)[1].strip().lower() or component_key
        else:
            component_type = plugin_type.lower() or component_key
        return ComponentRecord(
            script_name=script_name,
            component_key=component_key,
            component_type=component_type,
            folder=component_folder,
            descriptor_path=description_path,
            descriptor=descriptor,
        )
