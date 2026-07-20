from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import unique
from operator import is_
from pathlib import Path
import json
import re
from typing import Any, Generator

from .component_storage import ComponentDataStore, ComponentParameterStore, ComponentRecord
from rpp_plugin_registrator.library_manager import LibraryManager
from rpp_plugin_registrator.plugin_descriptors import parse_plugin_file
from .script_handle import (
    ScriptHandle,
    script_class_name_from_name,
    SCRIPT_LANGUAGES,
    DEFAULT_SCRIPT_LANGUAGE,
    language_spec,
    default_script_source
)


def _unique_name(base_name: str, existing_names: set[str]) -> str:
    base = base_name.strip() or "Component"
    if base not in existing_names:
        return base
    index = 2
    while True:
        candidate = f"{base} ({index})"
        if candidate not in existing_names:
            return candidate
        index += 1

def _json_load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))




class Workspace:
    script_dir_name: str = "scripts"
    script_descriptions_dir_name: str = "script_descriptions"
    parts_dir_name: str = "parts"
    data_dir_name: str = "data"
    builds_dir_name: str = "builds"
    logs_dir_name: str = "logs"
    default_script_language: str = DEFAULT_SCRIPT_LANGUAGE

    def __init__(self, root: Path, lib_manager: LibraryManager | None = None) -> None:
        self.root = root.expanduser().resolve()
        self.lib_manager = lib_manager or LibraryManager()
        self.component_data_store = ComponentDataStore(self.parts_path, lib_manager=self.lib_manager)
        self.part_records: dict[str, ComponentRecord] = {}
        self._load_part_records()

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
    def script_descriptions_path(self) -> Path:
        return self.root / self.script_descriptions_dir_name

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


    def get_component(self, component_id_or_name: str) -> ComponentRecord:
        if component_id_or_name in self.part_records:
            return self.part_records[component_id_or_name]
        for record in self.part_records.values():
            if record.name == component_id_or_name:
                return record
        raise ValueError(f"Component not found: {component_id_or_name}")

    def get_subcomponent(self, parent_component_id_or_name: str, slot_name: str) -> ComponentRecord | None:
        parent_record = self.get_component(parent_component_id_or_name)
        if not parent_record:
            raise ValueError(f"Parent component not found: {parent_component_id_or_name}")
        subcomponent_info = parent_record.subcomponents.get(slot_name)
        if not subcomponent_info:
            raise ValueError(f"Subcomponent not found: {slot_name}")
        if isinstance(subcomponent_info, list):
            return [self.get_component(sub.id) for sub in subcomponent_info]
        else:
            return self.get_component(subcomponent_info.id)



    def write_script(self, script_name: str, source: str, filename: str | None = None, language: str = DEFAULT_SCRIPT_LANGUAGE) -> Path:
        self.scripts_path.mkdir(parents=True, exist_ok=True)
        extension = language_spec(language).extension
        target = self.scripts_path / (filename or f"{script_name}{extension}")
        target.write_text(source, encoding="utf-8")
        return target

    def ensure_layout(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.scripts_path.mkdir(parents=True, exist_ok=True)
        self.script_descriptions_path.mkdir(parents=True, exist_ok=True)
        self.parts_path.mkdir(parents=True, exist_ok=True)
        self.data_path.mkdir(parents=True, exist_ok=True)
        self.builds_path.mkdir(parents=True, exist_ok=True)
        self.logs_path.mkdir(parents=True, exist_ok=True)

    def ensure_parts_layout(self) -> None:
        self.parts_path.mkdir(parents=True, exist_ok=True)

    def list_scripts(self) -> list[ScriptHandle]:
        self.scripts_path.mkdir(parents=True, exist_ok=True)
        scripts = []
        for script_file in self.scripts_path.iterdir():
            if script_file.is_file() and script_file.suffix in {spec.extension for spec in SCRIPT_LANGUAGES.values()}:
                language = next((lang for lang, spec in SCRIPT_LANGUAGES.items() if spec.extension == script_file.suffix), None)
                scripts.append(ScriptHandle(path=script_file, ws=self, language=language))
        return scripts


    def ensure_script_assignments(self, script_path: Path) -> None:
        assignments_path = self._script_assignments_path(script_path)
        if not assignments_path.exists():
            self.write_script_component_assignments(script_path, {})

    def create_script(self,
            script_name: str, source: str | None = None,
            language: str = DEFAULT_SCRIPT_LANGUAGE) -> ScriptHandle:
        self.scripts_path.mkdir(parents=True, exist_ok=True)
        extension = Path(script_name).suffix
        if extension:
            if extension not in {spec.extension for spec in SCRIPT_LANGUAGES.values()}:
                raise ValueError(f"Invalid script extension: {extension}")
            script_name = Path(script_name).stem
            target = self.scripts_path / f"{script_name}{extension}"
        else:
            script_name = Path(script_name).stem
            extension = language_spec(language).extension
            target = self.scripts_path / f"{script_name}{extension}"
        if source is not None:
            target.write_text(source, encoding="utf-8")
        else:
            name = script_class_name_from_name(script_name)
            default_source = default_script_source(name, language=language)
            target.write_text(default_source, encoding="utf-8")
        self.write_script_component_assignments(target, {})
        return ScriptHandle(path=target, ws=self, language=language)

    def delete_script(self, script_path: Path) -> None:
        if script_path.exists():
            script_path.unlink()

    def parse_plugin_and_get_parameters(self, plugin_info: dict[str, Any]) -> dict[str, Any]:
        plugin_file_relative_to_library = plugin_info.get("PluginPath")
        library = plugin_info.get("Library")
        class_name = plugin_info.get("ClassName")
        plugin_file = self.lib_manager.get_plugin_path_absolute(plugin_file_relative_to_library, library)
        parsed = parse_plugin_file(plugin_file)
        if not parsed.is_valid or not parsed.data.plugins:
            raise ValueError(f"Failed to parse plugin '{plugin_file}' for component creation.")
        for plugin_desc in parsed.data.plugins:
            if plugin_desc["ClassName"] == class_name:
                parameters = plugin_desc.get("ParamDescription", [])
                break
        return parameters

    def create_component(
        self,
        component_name: str,
        plugin_name: str,
        *,
        parameters: dict[str, Any] | list[Any] | None = None,
        overwrite: bool = False,
    ) -> ComponentRecord:
        self.ensure_parts_layout()
        unique_name = self.resolve_unique_component_name(component_name)
        info = self.lib_manager.get_plugin_info_from_lib(plugin_name)
        if parameters is None:
            parameters = self.parse_plugin_and_get_parameters(info)

        record = self.component_data_store.create_component_folder(
            unique_name, info,
            overwrite=overwrite,
            parameters=parameters
        )
        self.part_records[record.id] = record
        return record

    def assign_subcomponent(
        self,
        parent_folder: Path,
        slot_name: str,
        component_name: str,
        plugin_name: str,
        *,
        parameters: dict[str, Any] | list[Any] | None = None,
    ) -> ComponentRecord:

        parent_record = self.component_data_store.load_description(parent_folder)
        parent_plugin_info = self.lib_manager.get_plugin_info_from_lib(parent_record.plugin_name)  # Ensure plugin is loaded

        metadata = parent_plugin_info.get("PluginMetadata", {})
        components = metadata.get("Components", {})
        if slot_name not in components:
            raise ValueError(f"Plugin '{parent_record.plugin_name}' does not have a component slot named '{slot_name}'")

        subcomponent_info = self.lib_manager.get_plugin_info_from_lib(plugin_name)

        slot_type = components[slot_name]

        # overwrite component if it is not specified as a list in COMPONENTS field of the parent plugin
        allow_list = False
        overwrite = True
        if isinstance(slot_type, list):
            slot_type = slot_type[0]
            allow_list = True
            overwrite = False

        if slot_type != subcomponent_info["PluginType"]:
            raise ValueError(f"Plugin '{plugin_name}' has an invalid type for subcomponent field '{slot_name}'")

        component_name = self.resolve_unique_component_name(component_name)
        parent_record, child_record = self.component_data_store.create_subcomponent_folder(
            parent_record.folder,
            slot_name,
            component_name=component_name,
            plugin_info_or_name=subcomponent_info,
            parameters=parameters,
            overwrite=overwrite,
            allow_list=allow_list
        )

        self.component_data_store.save_description(child_record.folder, child_record)
        self.component_data_store.save_description(parent_record.folder, parent_record)
        self.part_records[child_record.id] = child_record
        self.part_records[parent_record.id] = parent_record
        return child_record

    def resolve_unique_component_name(self, requested_name: str) -> str:
        names = {record.name for record in self.part_records.values()}
        return _unique_name(requested_name, names)

    def read_part_descriptor(self, folder: Path) -> ComponentRecord:
        return self.component_data_store.load_description(folder)

    def write_part_descriptor(self, folder: Path, record: ComponentRecord) -> Path:
        return self.component_data_store.save_description(folder, record)

    def part_descriptor_path(self, folder: Path) -> Path:
        description_path = folder / "description.json"
        if description_path.exists():
            return description_path
        raise FileNotFoundError(f"No part descriptor JSON found in: {folder}")

    def part_parameters_path(self, folder: Path) -> Path:
        return self.component_parameter_store.parameters_path(folder)

    def get_part_records(self) -> dict[str, ComponentRecord]:
        return self.part_records

    def iterate_part_records(self) -> Generator[ComponentRecord, None, None]:
        for record in self.part_records.values():
            if record is not None:
                yield record

    def get_part_record_by_id(self, part_id: str) -> ComponentRecord | None:
        return self.part_records.get(part_id)

    def rename_script(self, script_path: Path, new_name: str, language: str | None = None) -> Path:
        ext = language_spec(language or self.default_script_language).extension if language else script_path.suffix
        target = script_path.with_name(f"{new_name}{ext}")
        if target.exists():
            raise FileExistsError(f"Target script already exists: {target}")
        script_path.rename(target)
        return target

    def _script_assignments_path(self, script_path: Path) -> Path:
        self.script_descriptions_path.mkdir(parents=True, exist_ok=True)
        return self.script_descriptions_path / f"{script_path.stem}.json"

    def read_script_component_assignments(self, script_path: Path) -> dict[str, list[str]]:
        assignments_path = self._script_assignments_path(script_path)
        if assignments_path.exists():
            try:
                payload = json.loads(assignments_path.read_text(encoding="utf-8"))
                if isinstance(payload, dict) and "Components" in payload:
                    return payload["Components"]
            except (json.JSONDecodeError, OSError):
                pass
        return None

    def remove_component_from_script(self, script_h: ScriptHandle, component_id: str, component_key: str | None) -> None:
        removed_id = component_id.strip()
        if not removed_id:
            raise ValueError("Component ID to remove cannot be empty.")

        if component_key is not None:
            key = component_key.strip()
        else:
            key = None

        assignments = self.read_script_component_assignments(script_h.path)
        if key is not None:
            component_ids = assignments.get(key)
            if not component_ids:
                return

            assignments[key] = [item for item in component_ids if item != removed_id]
            if not assignments[key]:
                assignments.pop(key, None)
        else:
            # Remove the component from all keys
            for k in list(assignments.keys()):
                component_ids = assignments[k]
                if removed_id in component_ids:
                    assignments[k] = [item for item in component_ids if item != removed_id]
                    if not assignments[k]:
                        assignments.pop(k, None)

        assignments_path = self._script_assignments_path(script_h.path)
        payload = self.build_assignments_payload(script_h.path, assignments)
        assignments_path.write_text(
            json.dumps(payload, indent=4, sort_keys=False),
            encoding="utf-8",
        )

    def remove_component(self, record_id: str) -> None:
        component_record = self.get_part_record_by_id(record_id)
        if not component_record:
            raise ValueError(f"Component with id '{record_id}' not found.")

        # remove the component from scripts
        for script_h in self.list_scripts():
            self.remove_component_from_script(script_h, component_id=component_record.id, component_key=None)

        self.component_data_store.remove_component_folder(component_record.folder)
        self.part_records.pop(component_record.id, None)

    def remove_subcomponent(self, parent_component_id_or_name: str, slot_name: str, subcomponent_id: str) -> None:
        parent_component = self.get_part_record_by_id(parent_component_id_or_name)
        if not parent_component:
            raise ValueError(f"Parent component with id '{parent_component_id_or_name}' not found.")

        if slot_name not in parent_component.subcomponents:
            raise ValueError(f"Slot '{slot_name}' not found in parent component '{parent_component.id}'.")

        msg = f"Subcomponent with id '{subcomponent_id}' not found in slot" + \
                f"'{slot_name}' of parent component '{parent_component.id}'."
        if not self.check_subcomponent_in_slot(parent_component.subcomponents, slot_name, subcomponent_id):
            raise ValueError(msg)

        parent_component.subcomponents = \
            self.remove_subcomponent_from_slot(parent_component.subcomponents, slot_name, subcomponent_id)

        self.component_data_store.remove_subcomponent_folder(self.get_part_record_by_id(subcomponent_id).folder)
        self.component_data_store.save_description(parent_component.folder, parent_component)
        self.part_records.pop(subcomponent_id, None)



    def remove_subcomponent_from_slot(self, parent_subcomponents, slot_name, subcomponent_id: str) -> None:
        slot_subcomponents = parent_subcomponents[slot_name]
        if isinstance(slot_subcomponents, list):
            parent_subcomponents[slot_name] = [sub for sub in slot_subcomponents if sub.id != subcomponent_id]
        else:
            parent_subcomponents.pop(slot_name, None)
        return parent_subcomponents

    def check_subcomponent_in_slot(self, parent_subcomponents, slot_name, subcomponent_id: str) -> bool:
        slot_subcomponents = parent_subcomponents[slot_name]
        if isinstance(slot_subcomponents, list):
            if subcomponent_id in [sub.id for sub in slot_subcomponents]:
                return True
        else:
            return slot_subcomponents.id == subcomponent_id

    def duplicate_component(self, record_id: str, new_name: str = None) -> ComponentRecord:

        if not new_name:
            new_name = self.get_part_record_by_id(record_id).name + "_copy"
        new_name = self.resolve_unique_component_name(new_name)

        component_record = self.get_part_record_by_id(record_id)
        if not component_record:
            raise ValueError(f"Component with id '{record_id}' not found.")

        duplicated_folder, duplicated_records = \
            self.component_data_store.duplicate_component_folder(component_record.folder, new_name)

        for k, v in duplicated_records.items():
            self.part_records[k] = v

        duplicated_record = self.component_data_store.load_description(duplicated_folder)
        return duplicated_record

    def write_script_component_assignments(self, script_path: Path, assignments: dict[str, list[str]]) -> None:
        assignments_path = self._script_assignments_path(script_path)
        payload = self.build_assignments_payload(script_path, assignments)
        assignments_path.write_text(
            json.dumps(payload, indent=4, sort_keys=False),
            encoding="utf-8",
        )

    def write_context(self, name: str, source: str, filename: str | None = None) -> Path:
        target = self.root / (filename or name)
        target.write_text(source, encoding="utf-8")
        return target

    def assign_component_to_script(self, script_h: ScriptHandle, component_key: str, record_id: str) -> None:
        """
        Assign a component to a script by updating the COMPONENTS dict in the script file.
        Uses read_script_components and write_script_components helpers.
        """
        if not script_h.path.exists():
            raise FileNotFoundError(f"Script not found: {script_h.path}")

        components = self.read_script_component_assignments(script_h.path)
        # Append to list for this key, or create new list
        existing = components.get(component_key)
        record = self.get_part_record_by_id(record_id)

        if record.plugin_type != script_h.slots.get(component_key):
            raise ValueError(f"Plugin type '{record.plugin_name}' does not match slot type '{script_h.slots.get(component_key)}' for slot '{component_key}'.")

        if isinstance(existing, list):
            if record.id not in existing:
                existing.append(record.id)
            components[component_key] = existing
        elif existing is not None:
            # Convert single id to list
            if existing != record.id:
                components[component_key] = [existing, record.id]
            else:
                components[component_key] = [existing]
        else:
            components[component_key] = [record.id]
        self.write_script_component_assignments(script_h.path, components)

    def build_assignments_payload(self, script_handle, assignments):
        return {
            "Components": assignments,
        }

    def _load_part_records(self):
        self.ensure_parts_layout()
        for record_path in self.component_data_store.iter_component_description_files():
            if record_path.name != "description.json":
                continue
            component_record = self.component_data_store.load_description(record_path.parent)
            self.part_records[component_record.id] = component_record



def open_workspace(ws_path: str | Path) -> Workspace:
    root_path = Path(ws_path).expanduser().resolve()
    if not root_path.exists() or not root_path.is_dir():
        raise FileNotFoundError(f"Workspace root does not exist or is not a directory: {root_path}")
    workspace = Workspace(root=root_path)
    return workspace

def create_workspace(root: str | Path, name: str | None = None, overwrite: bool = False) -> Workspace:
    root_path = Path(root).expanduser().resolve()
    if root_path.exists() and any(root_path.iterdir()) and not overwrite:
        raise FileExistsError(f"Workspace root already exists and is not empty: {root_path}")

    root_path.mkdir(parents=True, exist_ok=True)
    workspace = Workspace(root=root_path)
    workspace.ensure_layout()
    default_script_name = name or workspace.name
    extension = language_spec(workspace.default_script_language).extension
    default_script = workspace.scripts_path / f"{default_script_name}{extension}"
    if not default_script.exists():
        workspace.create_script(
            default_script_name,
            default_script_source(script_class_name_from_name(default_script_name), language=workspace.default_script_language),
            language=workspace.default_script_language,
        )
    return workspace
