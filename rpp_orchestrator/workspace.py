from __future__ import annotations

from pathlib import Path
import json
import shutil
from typing import Any, Generator
from rpp_plugin_registrator.library_manager import LibraryManager

from .component_storage import (
    ComponentDataStore,
    ComponentParameterStore,
    ComponentRecord,
    LinkedComponentRecord
)
from .script_handle import (
    ScriptHandle,
    get_script_language_from_path,
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


    @classmethod
    def workspace_exists(cls, root: Path) -> bool:
        rppws_folder = root / ".rppws"
        return rppws_folder.exists() and rppws_folder.is_dir()

    @classmethod
    def clear(cls) -> None:
        # Clear the workspace by removing the .rppws folder
        rppws_folder = Path(".rppws")
        if rppws_folder.exists() and rppws_folder.is_dir():
            shutil.rmtree(rppws_folder)

    @property
    def rppws_folder(self) -> Path:
        return self.root / ".rppws"

    @property
    def component_parameter_store(self) -> ComponentParameterStore:
        return self.component_data_store.parameters

    @property
    def name(self) -> str:
        return self.root.name

    @property
    def script_descriptions_path(self) -> Path:
        return self.rppws_folder / self.script_descriptions_dir_name

    @property
    def parts_path(self) -> Path:
        return self.rppws_folder / self.parts_dir_name

    @property
    def data_path(self) -> Path:
        return self.rppws_folder / self.data_dir_name

    @property
    def builds_path(self) -> Path:
        return self.rppws_folder / self.builds_dir_name

    @property
    def logs_path(self) -> Path:
        return self.rppws_folder / self.logs_dir_name


    def get_component(self, component_id_or_name: str) \
            -> ComponentRecord | LinkedComponentRecord:
        if component_id_or_name in self.part_records:
            return self.part_records[component_id_or_name]
        for record in self.part_records.values():
            if record.name == component_id_or_name:
                return record
        raise ValueError(f"Component not found: {component_id_or_name}")

    def get_subcomponent(self, parent_component_id_or_name: str, slot_name: str) \
            -> ComponentRecord | LinkedComponentRecord | None:
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

    def write_script(self, script_path: Path, source: str) -> Path:
        script_path.write_text(source, encoding="utf-8")
        return script_path

    def ensure_layout(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.script_descriptions_path.mkdir(parents=True, exist_ok=True)
        self.parts_path.mkdir(parents=True, exist_ok=True)
        self.data_path.mkdir(parents=True, exist_ok=True)
        self.builds_path.mkdir(parents=True, exist_ok=True)
        self.logs_path.mkdir(parents=True, exist_ok=True)

    def ensure_parts_layout(self) -> None:
        self.parts_path.mkdir(parents=True, exist_ok=True)

    def resolve_linked_folder(self,
            record_id: str) -> Path | None:
        record = self.get_component(record_id)
        if isinstance(record, ComponentRecord):
            return record.folder
        linked_record = self.get_component(record.linked_component_id)
        return linked_record.folder

    def list_scripts(self) -> list[ScriptHandle]:
        scripts = []
        script_descriptions_path = self.script_descriptions_path
        for script_file in script_descriptions_path.iterdir():
            if script_file.is_file() and script_file.suffix == ".json":
                json_data = _json_load(script_file)
                script_path = json_data.get("ScriptPath")
                if not Path(script_path).exists():
                    script_file.unlink()  # Remove the description if the script file doesn't exist
                    continue
                language = json_data.get("Language")
                scripts.append(ScriptHandle(path=Path(script_path), ws=self, language=language))
        return scripts

    def ensure_script_assignments(self, script_path: Path) -> None:
        assignments_path = self.get_script_description_path(script_path)
        if not assignments_path.exists():
            self.write_script_description(script_path, DEFAULT_SCRIPT_LANGUAGE, {})

    def load_script(self, script_path: Path) -> ScriptHandle:
        if not script_path.exists():
            raise FileNotFoundError(f"Script file does not exist: {script_path}")
        language = next((lang for lang, spec in SCRIPT_LANGUAGES.items() if spec.extension == script_path.suffix), None)
        return ScriptHandle(path=script_path, ws=self, language=language)

    def create_script(self,
            script_path_or_name: Path | str, source: str | None = None,
            language: str = DEFAULT_SCRIPT_LANGUAGE) -> ScriptHandle:

        script_path_or_name = Path(script_path_or_name)
        if not script_path_or_name.is_absolute():
            script_path = self.root / script_path_or_name
        else:
            script_path = script_path_or_name
        extension = script_path.suffix
        language = get_script_language_from_path(script_path) if extension else language
        if not extension:
            extension = language_spec(language).extension
            script_path = script_path.with_suffix(extension)


        if not script_path.relative_to(self.root):
            raise ValueError(f"Script path must be within the scripts directory: {self.root}")
        if extension:
            if extension not in {spec.extension for spec in SCRIPT_LANGUAGES.values()}:
                raise ValueError(f"Invalid script extension: {extension}")
            script_name = script_path.stem
        else:
            script_name = Path(script_name).stem
            extension = language_spec(language).extension
        if source is not None:
            script_path.write_text(source, encoding="utf-8")
        else:
            default_source = default_script_source(script_path=script_path)
            script_path.write_text(default_source, encoding="utf-8")
        self.write_script_description(script_path, language, {})
        return ScriptHandle(path=script_path, ws=self, language=language)

    def delete_script(self, script_path: Path) -> None:
        if script_path.exists():
            script_path.unlink()


    def is_linked_component_valid(self, linked_record: LinkedComponentRecord) -> bool:
        #TODO: Implement support for cross-workspace linked components in the future.
        try:
            linked_component = self.get_part_record_by_id(linked_record.linked_component_id)
            if not linked_component:
                return False
            return True
        except ValueError:
            return False

    def create_component(
        self,
        component_name: str,
        plugin_name: str,
        *,
        overwrite: bool = False,
    ) -> ComponentRecord:
        self.ensure_parts_layout()
        unique_name = self.resolve_unique_component_name(component_name)
        info = self.lib_manager.get_plugin_info_from_lib(plugin_name)

        record = self.component_data_store.create_component_folder(
            unique_name, info,
            overwrite=overwrite
        )
        self.part_records[record.id] = record
        return record

    def create_subcomponent(
        self,
        parent_folder: Path,
        slot_name: str,
        component_name: str,
        plugin_name: str,
    ) -> ComponentRecord:

        parent_record = self.component_data_store.load_description(parent_folder)
        subcomponent_info = \
            self.lib_manager.get_plugin_info_from_lib(plugin_name)

        slot_type, allow_list, overwrite = \
            self._get_slot_type_from_plugin(parent_record.plugin_name, slot_name)

        # overwrite component if it is not specified as a list in COMPONENTS field of the parent plugin

        if slot_type != subcomponent_info["PluginType"]:
            raise ValueError(f"Plugin '{plugin_name}'"
                + f" has an invalid type for subcomponent field '{slot_name}'")

        component_name = self.resolve_unique_component_name(component_name)
        parent_record, child_record = \
            self.component_data_store.create_subcomponent_folder(
                parent_record.folder,
                slot_name,
                component_name=component_name,
                plugin_info_or_name=subcomponent_info,
                overwrite=overwrite,
                allow_list=allow_list
        )

        self.component_data_store.save_description(child_record.folder, child_record)
        self.component_data_store.save_description(parent_record.folder, parent_record)
        self.part_records[child_record.id] = child_record
        self.part_records[parent_record.id] = parent_record
        return child_record

    def assign_subcomponent_to_parent(self,
            parent_component_id_or_name: str, slot_name: str,
            subcomponent_id: str) -> None:

        parent_record = self.get_part_record_by_id(parent_component_id_or_name)
        if not parent_record:
            raise ValueError(
                f"Parent component with id '{parent_component_id_or_name}' not found.")
        child_record = self.get_part_record_by_id(subcomponent_id)
        if not child_record:
            raise ValueError(
                f"Subcomponent with id '{subcomponent_id}' not found.")

        slot_type, allow_list, overwrite = \
            self._get_slot_type_from_plugin(parent_record.plugin_name, slot_name)

        if slot_type != child_record.plugin_type:
            raise ValueError(f"Plugin '{child_record.plugin_name}'"
                + f" has an invalid type for subcomponent field '{slot_name}'"
                + f" of parent plugin '{parent_record.plugin_name}'")

        parent_subcomponent_spec = parent_record.subcomponent_spec
        if slot_name not in parent_subcomponent_spec:
            raise ValueError(
                f"Slot '{slot_name}' not found in parent component '{parent_record.id}'.")

        parent_subcomponent_info = parent_subcomponent_spec[slot_name]

        if not allow_list and isinstance(parent_subcomponent_info, list):
            raise ValueError(
                f"Slot '{slot_name}' in parent component '{parent_record.id}'"
                + " does not allow multiple subcomponents.")

        parent_record, new_child = \
            self.component_data_store.create_linked_subcomponent_folder(
                parent_record, slot_name, child_record, self.name,
                overwrite=overwrite, allow_list=allow_list
            )
        self.part_records[new_child.id] = new_child
        self.part_records[parent_record.id] = parent_record

        self.component_data_store.save_description(new_child.folder, new_child)
        self.component_data_store.save_description(parent_record.folder, parent_record)

        return parent_record, new_child

    def resolve_unique_component_name(self, requested_name: str) -> str:
        names = {record.name for record in self.part_records.values()}
        return _unique_name(requested_name, names)

    def read_part_descriptor(self, folder: Path) \
            -> ComponentRecord | LinkedComponentRecord:
        return self.component_data_store.load_description(folder)

    def write_part_descriptor(self, folder: Path,
            record: ComponentRecord) -> Path:
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

    def get_linked_component(self,
            link_record: LinkedComponentRecord) -> ComponentRecord | None:
        return self.get_part_record_by_id(link_record.linked_component_id)


    def iterate_part_records(self, root_only: bool = False) \
            -> Generator[ComponentRecord, None, None]:
        for record in self.part_records.values():
            if record is not None \
                    and (not root_only or record.parent_component_info is None):
                yield record

    def get_part_record_by_id(self, part_id: str) -> ComponentRecord | None:
        return self.part_records.get(part_id)

    def rename_script(self,
            script_path: Path, new_name: str, language: str | None = None) -> Path:
        ext = language_spec(language or self.default_script_language).extension \
            if language else script_path.suffix
        target = script_path.with_name(f"{new_name}{ext}")
        if target.exists():
            raise FileExistsError(f"Target script already exists: {target}")
        script_path.rename(target)
        return target

    def get_script_description_path(self, script_path: Path) -> Path:
        self.script_descriptions_path.mkdir(parents=True, exist_ok=True)
        return self.script_descriptions_path / f"{script_path.stem}.json"

    def read_script_description(self, script_path: Path) -> dict[str, list[str]]:
        assignments_path = self.get_script_description_path(script_path)
        if assignments_path.exists():
            try:
                payload = json.loads(assignments_path.read_text(encoding="utf-8"))
                return payload
            except (json.JSONDecodeError, OSError):
                pass
        return None

    def remove_component_from_script(self,
            script_h: ScriptHandle, component_id: str, component_key: str | None) -> None:
        removed_id = component_id.strip()
        if not removed_id:
            raise ValueError("Component ID to remove cannot be empty.")

        if component_key is not None:
            key = component_key.strip()
        else:
            key = None

        description = self.read_script_description(script_h.path)
        assignments = description.get("Components", {}) if description else {}
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

        self.write_script_description(script_h.path, script_h.language, assignments)

    def remove_component(self, record_id: str) -> None:
        component_record = self.get_part_record_by_id(record_id)
        if not component_record:
            raise ValueError(f"Component with id '{record_id}' not found.")

        # if the component is not a subcomponent, remove it from scripts
        parent_component_info = component_record.parent_component_info
        is_subcomponent = parent_component_info is not None
        if is_subcomponent:
            return self.remove_subcomponent(
                parent_component_id_or_name=parent_component_info.id,
                slot_name=parent_component_info.slot_name,
                subcomponent_id=component_record.id,
                handle_parent_update=True
            )

        if not self.can_remove_component(record_id):
            raise ValueError(f"Cannot remove component '{record_id}' "
                + "because it is assigned to scripts or has subcomponents.")

        for script_h in self.list_scripts():
            self.remove_component_from_script(script_h,
                    component_id=component_record.id, component_key=None)

        for key, subcomponent in component_record.subcomponents.items():
            if not isinstance(subcomponent, list):
                subcomponent = [subcomponent]
            for subc in subcomponent:
                self.remove_subcomponent(
                    record_id, key, subc.id, handle_parent_update=False)
        self.component_data_store.remove_component_folder(component_record.folder)
        self.part_records.pop(component_record.id, None)

    def remove_subcomponent(self,
            parent_component_id_or_name: str, slot_name: str,
            subcomponent_id: str, handle_parent_update: bool = False) -> None:
        parent_component = self.get_part_record_by_id(parent_component_id_or_name)
        if not parent_component:
            raise ValueError(
                f"Parent component with id '{parent_component_id_or_name}' not found.")

        if slot_name not in parent_component.subcomponents:
            raise ValueError(
                f"Slot '{slot_name}' not found in parent component '{parent_component.id}'.")

        msg = f"Subcomponent with id '{subcomponent_id}' not found in slot" + \
                f"'{slot_name}' of parent component '{parent_component.id}'."
        if not self.check_subcomponent_in_slot(
                parent_component.subcomponents, slot_name, subcomponent_id):
            raise ValueError(msg)

        if handle_parent_update:
            parent_component.subcomponents = \
                self.remove_subcomponent_from_slot(
                    parent_component.subcomponents, slot_name, subcomponent_id)
            self.component_data_store.save_description(
                parent_component.folder, parent_component)

        self.component_data_store.remove_subcomponent_folder(
            self.get_part_record_by_id(subcomponent_id).folder)
        self.part_records.pop(subcomponent_id, None)

    def remove_subcomponent_from_slot(self,
            parent_subcomponents, slot_name, subcomponent_id: str) -> None:
        slot_subcomponents = parent_subcomponents[slot_name]
        if isinstance(slot_subcomponents, list):
            parent_subcomponents[slot_name] = \
                [sub for sub in slot_subcomponents if sub.id != subcomponent_id]
        else:
            parent_subcomponents.pop(slot_name, None)
        return parent_subcomponents

    def check_subcomponent_in_slot(self,
            parent_subcomponents, slot_name, subcomponent_id: str) -> bool:
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

        if isinstance(component_record, LinkedComponentRecord):
            raise ValueError(f"Cannot duplicate a linked component: {record_id}")

        duplicated_folder, duplicated_records = \
            self.component_data_store.duplicate_component_folder(component_record.folder, new_name)

        for k, v in duplicated_records.items():
            self.part_records[k] = v

        duplicated_record = self.component_data_store.load_description(duplicated_folder)
        return duplicated_record

    def write_script_description(self,
            script_path: Path, language: str, assignments: dict[str, list[str]]) -> None:
        assignments_path = self.get_script_description_path(script_path)
        payload = self.build_assignments_payload(script_path, language, assignments)
        assignments_path.write_text(
            json.dumps(payload, indent=4, sort_keys=False),
            encoding="utf-8",
        )

    def write_context(self, name: str, source: str, filename: str | None = None) -> Path:
        target = self.root / (filename or name)
        target.write_text(source, encoding="utf-8")
        return target

    def assign_component_to_script(self,
            script_h: ScriptHandle, component_key: str, record_id: str) -> None:
        """
        Assign a component to a script by updating the COMPONENTS dict in the script file.
        Uses read_script_components and write_script_components helpers.
        """
        if not script_h.path.exists():
            raise FileNotFoundError(f"Script not found: {script_h.path}")

        description = self.read_script_description(script_h.path)
        # Append to list for this key, or create new list
        components = description.get("Components", {}) if description else {}
        existing = components.get(component_key)
        record = self.get_part_record_by_id(record_id)

        if record.plugin_type != script_h.slots.get(component_key):
            raise ValueError(f"Plugin type '{record.plugin_name}'"
                + f" does not match slot type '{script_h.slots.get(component_key)}'"
                + f" for slot '{component_key}'.")

        new_item = {
            "Id": record.id,
            "PluginName": record.plugin_name,
        }

        if isinstance(existing, list):
            if not any(item.get("Id") == record.id for item in existing):
                existing.append(new_item)
            components[component_key] = existing
        elif existing is not None:
            # Convert single id to list
            if existing["Id"] == record.id:
                components[component_key] = [existing, new_item]
            else:
                components[component_key] = [existing]
        else:
            components[component_key] = [new_item]
        self.write_script_description(script_h.path, script_h.language, components)

    def build_assignments_payload(self, script_path, language, assignments):
        return {
            "ScriptPath": str(script_path),
            "Language": language,
            "Components": assignments,
        }

    def can_remove_component(self, record_id: str) -> bool:
        for c in self.part_records.values():
            if isinstance(c, LinkedComponentRecord) and c.linked_component_id == record_id:
                return False
        return True



    def _get_slot_type_from_plugin(self, plugin_name: str, slot_name: str) -> str | None:
        parent_plugin_info = \
            self.lib_manager.get_plugin_info_from_lib(plugin_name)

        metadata = parent_plugin_info.get("PluginMetadata", {})
        components = metadata.get("Components", {})
        if slot_name not in components:
            raise ValueError(f"Plugin '{plugin_name}'"
                + f" does not have a component slot named '{slot_name}'")
        if slot_name not in components:
            raise ValueError(f"Plugin '{plugin_name}'"
                + f" does not have a component slot named '{slot_name}'")

        slot_type = components[slot_name]
        allow_list = False
        overwrite = True
        if isinstance(slot_type, list):
            slot_type = slot_type[0]
            allow_list = True
            overwrite = False

        return slot_type, allow_list, overwrite

    def _load_part_records(self):
        self.ensure_parts_layout()
        for record_path in self.component_data_store.iter_component_description_files():
            if record_path.name != "description.json":
                continue
            component_record = self.component_data_store.load_description(record_path.parent)
            self.part_records[component_record.id] = component_record

def open_workspace(ws_path: str | Path, lib_manager: LibraryManager | None = None) -> Workspace:
    root_path = Path(ws_path).expanduser().resolve()
    if not root_path.exists() or not root_path.is_dir():
        raise FileNotFoundError(
            f"Workspace root does not exist or is not a directory: {root_path}")
    workspace = Workspace(root=root_path, lib_manager=lib_manager)
    return workspace

def create_workspace(root: str | Path,
        name: str | None = None, overwrite: bool = False,
        lib_manager: LibraryManager | None = None) -> Workspace:
    root_path = Path(root).expanduser().resolve()
    exists = Workspace.workspace_exists(root_path)
    if exists and not overwrite:
        raise FileExistsError(
            f"Workspace root already exists and is not empty: {root_path}"
        )
    if exists:
        Workspace.clear()
    root_path.mkdir(parents=True, exist_ok=True)
    workspace = Workspace(root=root_path, lib_manager=lib_manager)
    workspace.ensure_layout()
    default_script_name = name or f"new_{workspace.name}_script"
    extension = language_spec(workspace.default_script_language).extension
    default_script = workspace.root / f"{default_script_name}{extension}"
    if not default_script.exists():
        workspace.create_script(
            script_path_or_name=default_script,
            source=default_script_source(script_path=default_script),
            language=workspace.default_script_language,
        )
    return workspace
