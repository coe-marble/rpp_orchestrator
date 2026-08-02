from __future__ import annotations

from dataclasses import dataclass, field, replace as dataclasses_replace
import importlib.util
import keyword
from pathlib import Path
from typing import Any
from uuid import uuid4
import json
import shutil

from .layout import ComponentLayout, default_component_layout
from rpp_plugin_registrator import plugin_id_from_name

from rpp_plugin_registrator.library_manager import LibraryManager


@dataclass(frozen=True)
class ParentComponentInfo:
    id: str
    plugin_type: str
    plugin_name: str
    slot_name: str
    library: str
    is_linked: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "Id": self.id,
            "PluginType": self.plugin_type,
            "PluginName": self.plugin_name,
            "SlotName": self.slot_name,
            "Library": self.library,
            "IsLinked": self.is_linked,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "ParentComponentInfo":
        return cls(
            id=str(data["Id"]),
            plugin_type=str(data["PluginType"]),
            plugin_name=str(data["PluginName"]),
            slot_name=str(data["SlotName"]),
            library=str(data["Library"]),
            is_linked=bool(data.get("IsLinked", False)),
        )

@dataclass(frozen=True)
class SubcomponentInfo:
    id: str
    plugin_type: str
    plugin_name: str
    slot_name: str
    library: str
    folder: Path
    is_linked: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "Id": self.id,
            "PluginType": self.plugin_type,
            "PluginName": self.plugin_name,
            "SlotName": self.slot_name,
            "Library": self.library,
            "Folder": str(self.folder),
            "IsLinked": self.is_linked,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "SubcomponentInfo":
        return cls(
            id=str(data["Id"]),
            plugin_type=str(data["PluginType"]),
            plugin_name=str(data["PluginName"]),
            slot_name=str(data["SlotName"]),
            library=str(data["Library"]),
            folder=Path(data["Folder"]),
            is_linked=bool(data.get("IsLinked", False)),
        )

@dataclass(frozen=False)
class LinkedComponentRecord:
    id: str
    name: str
    folder: Path
    linked_component_id: str
    linked_component_workspace: str
    parent_component_info: ParentComponentInfo

    def to_dict(self) -> dict[str, object]:
        return {
            "Id": self.id,
            "Name": self.name,
            "LinkedComponentId": self.linked_component_id,
            "LinkedComponentWorkspace": self.linked_component_workspace,
            "ParentComponentInfo": self.parent_component_info.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, object], description_path: Path) -> "LinkedComponentRecord":
        if isinstance(description_path, str):
            description_path = Path(description_path)
        folder = description_path.parent
        return cls(
            id=str(data["Id"]),
            name=str(data["Name"]),
            folder=folder,
            linked_component_id=str(data["LinkedComponentId"]),
            linked_component_workspace=str(data["LinkedComponentWorkspace"]),
            parent_component_info=ParentComponentInfo.from_dict(data["ParentComponentInfo"]),
        )

@dataclass(frozen=False)
class ComponentRecord:
    id: str
    name: str
    plugin_type: str
    plugin_name: str
    library: str
    folder: Path
    subcomponent_spec: dict[str, str]
    subcomponents: dict[str, SubcomponentInfo] = field(default_factory=dict)
    parent_component_info: ParentComponentInfo | None = None

    def to_dict(self) -> dict[str, object]:

        parsed_subcomponents = {}
        if self.subcomponents is not None:
            for key, sub in self.subcomponents.items():
                if isinstance(sub, list):
                    parsed_subcomponents = {key: [s.to_dict() for s in sub] \
                        for key, sub in self.subcomponents.items()}
                else:
                    parsed_subcomponents = {key: sub.to_dict() \
                        for key, sub in self.subcomponents.items()}
        return {
            "Id": self.id,
            "Name": self.name,
            "PluginType": self.plugin_type,
            "PluginName": self.plugin_name,
            "Library": self.library,
            "SubcomponentSpec": self.subcomponent_spec,
            "Subcomponents": parsed_subcomponents,
            "ParentComponentInfo": dict(self.parent_component_info.to_dict()) \
                if self.parent_component_info else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object],
            description_path: Path | str) -> "ComponentRecord":
        if isinstance(description_path, str):
            description_path = Path(description_path)
        folder = description_path.parent

        parsed_subcomponents = {}
        if data.get("Subcomponents") is not None:
            for key, sub in data["Subcomponents"].items():
                if isinstance(sub, list):
                    parsed_subcomponents[key] = \
                        [SubcomponentInfo.from_dict(s) for s in sub]
                else:
                    parsed_subcomponents[key] = \
                        SubcomponentInfo.from_dict(sub)

        return cls(
            id=str(data["Id"]),
            name=str(data["Name"]),
            plugin_type=str(data["PluginType"]),
            plugin_name=str(data["PluginName"]),
            library=str(data["Library"]),
            folder=folder,
            subcomponent_spec=data.get("SubcomponentSpec"),
            subcomponents=parsed_subcomponents,
            parent_component_info=
                ParentComponentInfo.from_dict(data["ParentComponentInfo"]) \
                    if data.get("ParentComponentInfo") else None,
        )

class ComponentParameterStore:
    def __init__(self, layout: ComponentLayout | None = None, lib_manager: LibraryManager | None = None):
        self.layout = layout or default_component_layout()
        self.lib_manager = lib_manager

    def parameters_path(self, component_folder: Path) -> Path:
        return component_folder / self.layout.params_dir / self.layout.parameters_filename

    def load(self, component_folder: Path) -> dict[str, Any]:
        params_path = self.parameters_path(component_folder)
        if not params_path.exists():
            return {}
        spec = importlib.util.spec_from_file_location("rpp_component_parameters", params_path)
        if spec is None or spec.loader is None:
            return {}

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        params_class = getattr(module, "ComponentParameters", None)
        if params_class is None:
            return {}

        loaded: dict[str, Any] = {}
        for name, value in vars(params_class).items():
            if name.startswith("_"):
                continue
            if callable(value):
                continue
            loaded[name] = _python_safe_value(value)
        return loaded

    def save(self, component_folder: Path, payload: dict[str, Any]) -> Path:
        params_path = self.parameters_path(component_folder)
        params_path.parent.mkdir(parents=True, exist_ok=True)
        normalized = _normalize_parameters_payload(payload)
        params_path.write_text(
            _build_component_parameters_source(normalized), encoding="utf-8")
        return params_path


    def ensure_parameters_file(self,
            component_folder: Path, payload: dict[str, Any] | None = None) -> Path:
        params_path = self.parameters_path(component_folder)
        params_path.parent.mkdir(parents=True, exist_ok=True)
        params_path.write_text(
            _build_component_parameters_source(payload or {}), encoding="utf-8")
        return params_path

    def clone_parameters_file(self,
            source_component_folder: Path, target_component_folder: Path) -> Path:
        source_params_path = self.parameters_path(source_component_folder)
        target_params_path = self.parameters_path(target_component_folder)
        target_params_path.parent.mkdir(parents=True, exist_ok=True)

        if source_params_path.exists():
            target_params_path.write_text(
                source_params_path.read_text(encoding="utf-8"), encoding="utf-8")
            return target_params_path

        return self.ensure_parameters_file(target_component_folder)

def _python_safe_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _python_safe_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_python_safe_value(item) for item in value]
    if isinstance(value, tuple):
        return [_python_safe_value(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "tolist") and callable(value.tolist):
        try:
            return _python_safe_value(value.tolist())
        except Exception:
            return repr(value)
    if callable(value):
        return None
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _python_literal(value: Any) -> str:
    if value is None:
        return "None"
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value == float("inf"):
            return 'float("inf")'
        if value == float("-inf"):
            return 'float("-inf")'
        if value != value:
            return 'float("nan")'
        return repr(value)
    if isinstance(value, str):
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(_python_literal(item) for item in value) + "]"
    if isinstance(value, tuple):
        if len(value) == 1:
            return f"({_python_literal(value[0])},)"
        return "(" + ", ".join(_python_literal(item) for item in value) + ")"
    if isinstance(value, dict):
        items = ", ".join(
            f"{_python_literal(str(key))}: {_python_literal(item)}" \
                for key, item in value.items())
        return "{" + items + "}"
    return repr(str(value))


def _build_component_parameters_source(payload: dict[str, Any]) -> str:
    lines = ["from __future__ import annotations",
        "", "", "class ComponentParameters:"]

    for name, value in payload.items():
        if "default_value" not in value:
            lines.append(f"    {name} = None")
            continue
        lines.append(
            f"    {name} = {_python_literal(value['default_value'])}")
    if len(payload) == 0:
        lines.append("    pass")

    lines.append("")
    return "\n".join(lines)


def _parameter_name(entry: Any) -> str | None:
    if isinstance(entry, dict):
        name = entry.get("Name", entry.get("name"))
    else:
        name = getattr(entry, "Name", getattr(entry, "name", None))
    if name is None:
        return None
    text = str(name).strip()
    return text or None


def _parameter_default_value(entry: Any) -> Any:
    if isinstance(entry, dict):
        if "DefaultValue" in entry:
            return entry["DefaultValue"]
        return entry.get("default_value")
    if hasattr(entry, "DefaultValue"):
        return getattr(entry, "DefaultValue")
    return getattr(entry, "default_value", None)


def _normalize_parameters_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload, dict):
        return {
            str(key): _python_safe_value(value) \
                for key, value in payload.items()
        }

    normalized: dict[str, Any] = {}
    for entry in payload:
        name = _parameter_name(entry)
        if name is None:
            continue
        normalized[name] = \
        _python_safe_value(_parameter_default_value(entry))
    return normalized


class ComponentDataStore:
    def __init__(self, parts_root: Path,
            layout: ComponentLayout | None = None,
            lib_manager: LibraryManager | None = None):
        self.parts_root = Path(parts_root)
        self.layout = layout or default_component_layout()
        self.parameters = ComponentParameterStore(self.layout, lib_manager)
        self.lm = lib_manager

    def component_options_root(self, plugin_id: str) -> Path:
        return self.parts_root / plugin_id

    def component_folder(self, plugin_id: str, component_id: str) -> Path:
        return self.component_options_root(plugin_id) / component_id

    def description_path(self, component_folder: Path) -> Path:
        return component_folder / self.layout.description_filename

    def callbacks_path(self, component_folder: Path) -> Path:
        return component_folder / self.layout.callbacks_filename

    def data_path(self, component_folder: Path) -> Path:
        return component_folder / self.layout.data_dir

    def subcomponents_path(self, component_folder: Path) -> Path:
        return component_folder / self.layout.subcomponents_dir

    def save_description(self, component_folder: Path,
            record: ComponentRecord | LinkedComponentRecord) -> Path:
        payload = record.to_dict()
        description_path = self.description_path(component_folder)
        description_path.parent.mkdir(parents=True, exist_ok=True)
        description_path.write_text(
            json.dumps(payload, indent=4, sort_keys=False), encoding="utf-8")
        return description_path

    def _with_parent_component_id(self,
            component_folder: Path, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(payload)
        parent_component_id = self._infer_parent_component_id(component_folder)
        if parent_component_id is not None:
            normalized.setdefault("ParentComponentId", parent_component_id)
        return normalized

    def _infer_parent_component_id(self,
            component_folder: Path) -> str | None:
        parts = component_folder.parts
        try:
            subcomponents_index = \
                parts.index(self.layout.subcomponents_dir)
        except ValueError:
            return None

        if subcomponents_index == 0:
            return None

        # .../<parent_uuid>/subcomponents/<slot>/options/<component_uuid>
        return parts[subcomponents_index - 1]

    def load_description(self,
            component_folder: Path,
            with_fields: dict[str, Any] | None = None) \
            -> ComponentRecord | LinkedComponentRecord:
        description_path = self.description_path(component_folder)
        return self._load_record(description_path, with_fields=with_fields)

    def ensure_component_folder(self,
            component_folder: Path,
            parameters: dict[str, Any] | list[Any] | None = None) -> None:
        component_folder.mkdir(parents=True, exist_ok=True)
        self.data_path(component_folder).mkdir(parents=True, exist_ok=True)
        self.subcomponents_path(component_folder).mkdir(parents=True, exist_ok=True)
        self.parameters.ensure_parameters_file(component_folder, parameters)
        callbacks_path = self.callbacks_path(component_folder)
        if not callbacks_path.exists():
            callbacks_path.write_text(
                "from __future__ import annotations\n", encoding="utf-8")

    def create_component_folder(
        self, component_name: str,
        plugin_info_or_name : dict[str, Any] | str,
        *,
        overwrite: bool = False,
    ) -> ComponentRecord:
        record_id = str(uuid4())

        if isinstance(plugin_info_or_name, str):
            plugin_name = plugin_info_or_name
            plugin_info = self.lm.get_plugin_info_from_lib(plugin_name)
        else:
            plugin_info : dict[str, Any] = plugin_info_or_name
        plugin_name = plugin_info["PluginName"]
        lib_name = plugin_info["Library"]
        folder = self.component_folder(plugin_id_from_name(plugin_name), record_id)

        if folder.exists() and not overwrite:
            raise FileExistsError(f"Component folder already exists: {folder}")

        parameters = plugin_info["PluginMetadata"].get("Parameters", {})
        folder.mkdir(parents=True, exist_ok=True)
        self.ensure_component_folder(folder, parameters)

        subcomponent_spec = plugin_info["PluginMetadata"].get("Components", {})

        record = ComponentRecord(
            id=record_id,
            name=component_name,
            plugin_name=plugin_name,
            plugin_type=plugin_info["PluginType"],
            library=lib_name,
            folder=folder,
            subcomponent_spec=subcomponent_spec
        )
        self.save_description(folder, record)
        return record


    def create_linked_subcomponent_folder(
        self,
        parent_record: ComponentRecord,
        slot_name: str,
        link_record: ComponentRecord,
        workspace_name: str,
        *,
        overwrite: bool = False,
        allow_list: bool = False
    ) -> tuple[ComponentRecord, LinkedComponentRecord]:

        new_id = str(uuid4())
        folder = self.subcomponents_path(parent_record.folder) / new_id
        new_child = LinkedComponentRecord(
            id = new_id,
            name = link_record.name,
            linked_component_id = link_record.id,
            linked_component_workspace = str(workspace_name),
            folder = folder,
            parent_component_info = ParentComponentInfo(
                id=parent_record.id,
                plugin_type=parent_record.plugin_type,
                plugin_name=parent_record.plugin_name,
                slot_name=slot_name,
                library=parent_record.library,
            )
        )

        child_component_info = SubcomponentInfo(
            id=new_child.id,
            plugin_type=link_record.plugin_type,
            plugin_name=link_record.plugin_name,
            library=link_record.library,
            folder=link_record.folder,
            slot_name=slot_name,
            is_linked=True
        )

        if allow_list:
            subcomponent_container = parent_record.subcomponents.get(slot_name, [])
            idx = next((i for i, sub in enumerate(subcomponent_container) \
                    if sub.id == link_record.id), None)
            if idx is None:
                subcomponent_container.append(child_component_info)
            else:
                subcomponent_container[idx] = child_component_info
        else:
            parent_record.subcomponents[slot_name] = child_component_info

        return parent_record, new_child


    def create_subcomponent_folder(
        self,
        parent_component_folder: Path,
        slot_name: str,
        component_name: str,
        plugin_info_or_name: dict[str, Any] | str,
        *,
        overwrite: bool = False,
        allow_list: bool = False
    ) -> ComponentRecord:

        if isinstance(plugin_info_or_name, str):
            plugin_info = self.lm.get_plugin_info_from_lib(plugin_info_or_name)
        else:
            plugin_info : dict[str, Any] = plugin_info_or_name

        plugin_name = plugin_info["PluginName"]
        plugin_type = plugin_info["PluginType"]
        subcomponent_spec = plugin_info["PluginMetadata"].get("Components", {})
        record_id = str(uuid4())
        lib_name, _ = self.lm.parse_plugin_name(plugin_name)
        folder = self.subcomponents_path(parent_component_folder) / record_id
        if folder.exists() and not overwrite:
            raise FileExistsError(f"Component folder already exists: {folder}")
        parent_record : ComponentRecord = self.load_description(parent_component_folder)

        if overwrite:
            self._handle_overwrite_subcomponent(parent_record, slot_name, allow_list)

        record = ComponentRecord(
            id=record_id,
            name=component_name,
            plugin_type=plugin_type,
            plugin_name=plugin_name,
            library=lib_name,
            folder=folder,
            subcomponent_spec=subcomponent_spec,
            parent_component_info=ParentComponentInfo(
                id=parent_record.id,
                plugin_type=parent_record.plugin_type,
                plugin_name=parent_record.plugin_name,
                slot_name=slot_name,
                library=parent_record.library
            )
        )

        folder.mkdir(parents=True, exist_ok=True)
        parameters = plugin_info["PluginMetadata"].get("Parameters", {})
        self.ensure_component_folder(folder, parameters)

        sub_info = SubcomponentInfo(
            id=record_id,
            plugin_type=plugin_type,
            plugin_name=plugin_name,
            slot_name=slot_name,
            library=lib_name,
            folder=folder,
            is_linked=False
        )
        if allow_list:
            current_list = parent_record.subcomponents.get(slot_name)
            if not isinstance(current_list, list):
                current_list = [current_list] if current_list else []
            current_list.append(sub_info)
            parent_record.subcomponents[slot_name] = current_list
        else:
            parent_record.subcomponents[slot_name] = sub_info
        return parent_record, record


    def _handle_overwrite_subcomponent(self,
            parent_record: ComponentRecord, slot_name: str, allow_list: bool) -> None:
        subcomponents = parent_record.subcomponents or {}
        subcomponent_list = subcomponents.get(slot_name)
        if not isinstance(subcomponent_list, list):
            subcomponent_list = [subcomponent_list] if subcomponent_list else []

        for curr_subcomponent in subcomponent_list:
            self.remove_subcomponent_folder(curr_subcomponent.folder)
            del parent_record.subcomponents[slot_name]

    def iter_component_description_files(self) -> list[Path]:
        if not self.parts_root.exists():
            return []
        return sorted(path for path in self.parts_root.glob("**/description.json") \
            if path.is_file())

    def parse_component_location(self, description_path: Path) -> tuple[str, str, Path]:
        relative = description_path.relative_to(self.parts_root)
        parts = relative.parts
        if len(parts) < 2 or description_path.name != self.layout.description_filename:
            raise ValueError(f"Invalid component path: {description_path}")

        # New layout: <plugin_id>/<component_id>/...
        plugin_id = parts[0]
        component_id = parts[1] if len(parts) > 1 else ""
        component_folder = description_path.parent

        return plugin_id, component_id, component_folder

    def duplicate_component_folder(self, component_folder: Path, new_name: str) -> Path:
        if not component_folder.exists():
            raise FileNotFoundError(f"Component folder does not exist: {component_folder}")
        description_path = self.description_path(component_folder)
        record = self._load_record(description_path)
        new_record_id = str(uuid4())
        new_folder = self.component_folder(plugin_id_from_name(record.plugin_name), new_record_id)

        if new_folder.exists():
            raise FileExistsError(f"Target component folder already exists: {new_folder}")

        new_component_records = {}

        new_folder.parent.mkdir(parents=True, exist_ok=True)
        self._copy_component_folder(component_folder, new_folder)
        self._setup_duplicated_components_recursive(new_folder,
                target_id=new_record_id,
                target_name=new_name,
                parent_component_id=None,
                new_component_records=new_component_records)
        return new_folder, new_component_records

    def remove_component_folder(self, component_folder: Path) -> None:
        if not component_folder.exists():
            return
        shutil.rmtree(component_folder)
        if component_folder.parent.exists() and not any(component_folder.parent.iterdir()):
            component_folder.parent.rmdir()

    def rename_component_folder(self, component_folder: Path, new_name: str) -> None:
        if not component_folder.exists():
            raise FileNotFoundError(f"Component folder does not exist: {component_folder}")
        description_path = self.description_path(component_folder)
        record = self._load_record(description_path)
        record.name = new_name
        self.save_description(component_folder, record)
        return record

    def change_component_plugin_name(self,
            component_folder: Path, new_plugin_name: str) -> None:
        if not component_folder.exists():
            raise FileNotFoundError(
                f"Component folder does not exist: {component_folder}")
        description_path = self.description_path(component_folder)
        record : ComponentRecord = self._load_record(description_path)
        lib_name, _ = self.lm.parse_plugin_name(new_plugin_name)
        record.library = lib_name
        record.plugin_name = new_plugin_name
        # now, move the component folder to the new location based on the new plugin name
        new_folder = self.component_folder(plugin_id_from_name(new_plugin_name), record.id)

        if new_folder.exists():
            raise FileExistsError(f"Target component folder already exists: {new_folder}")
        new_folder.parent.mkdir(parents=True, exist_ok=True)
        component_folder.rename(new_folder)
        record.folder = new_folder
        self.save_description(new_folder, record)
        return record

    def remove_subcomponent_folder(self,
            subcomponent_folder: Path) -> None:
        self.remove_component_folder(subcomponent_folder)

    def _load_record(self,
            description_path: Path,
            with_fields: dict[str, Any] | None = None) \
            -> ComponentRecord | LinkedComponentRecord:
        data = json.loads(description_path.read_text(encoding="utf-8"))
        data.update(with_fields or {})
        if "LinkedComponentId" in data:
            return LinkedComponentRecord.from_dict(data, description_path)
        return ComponentRecord.from_dict(data, description_path)

    def _copy_component_folder(self,
            source_folder: Path, target_folder: Path) -> None:
        shutil.copytree(source_folder, target_folder)


    def _setup_duplicated_components_recursive(self, target_folder: Path,
            target_id: str, target_name: str | None,
            parent_component_id: str | None = None,
            new_component_records: dict[str, ComponentRecord] | None = None) \
                -> None:

        fields = {"Id": target_id}
        if target_name:
            fields["Name"] = target_name
        record = self.load_description(target_folder, with_fields=fields)

        if parent_component_id is not None:
            if record.parent_component_info is None:
                assert False, \
                    "Parent component info should not be None " \
                    + "when duplicating a subcomponent."

        if parent_component_id is not None:
            record.parent_component_info = \
                dataclasses_replace(record.parent_component_info, id=parent_component_id)

        if isinstance(record, LinkedComponentRecord):
            # For linked components, we don't duplicate the linked component itself,
            # but we still need to update the parent component info.
            new_component_records[record.id] = record
            self.save_description(target_folder, record)
            return


        def handle_child_subcomponent(sub: SubcomponentInfo,
                target_folder: Path,
                new_component_records: dict[str, ComponentRecord]) -> None:
            old_id = sub.id
            sub_folder = self.subcomponents_path(target_folder) / old_id
            new_target_id = str(uuid4())
            new_folder = self.subcomponents_path(target_folder) / new_target_id
            # rename with new id
            shutil.move(sub_folder, new_folder)
            self._setup_duplicated_components_recursive(new_folder,
                    new_target_id, None, record.id, new_component_records)
            return dataclasses_replace(sub, id=new_target_id, folder=new_folder)

        if record.subcomponents:
            for slot_name, sub_info in record.subcomponents.items():
                if isinstance(sub_info, list):
                    new_sub_info = []
                    for sub in sub_info:
                        new_sub_info_v = handle_child_subcomponent(
                            sub, target_folder, new_component_records)
                        new_sub_info.append(new_sub_info_v)
                else:
                    new_sub_info = handle_child_subcomponent(
                        sub_info, target_folder, new_component_records)
                record.subcomponents[slot_name] = new_sub_info

        new_component_records[record.id] = record
        self.save_description(target_folder, record)