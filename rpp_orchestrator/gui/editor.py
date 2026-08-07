from __future__ import annotations

import importlib.util
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
import json
import shutil as path_shutil
from typing import Any
from uuid import uuid4

from PyQt6.QtCore import QSignalBlocker, QTimer, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QLineEdit,
    QStyle,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
from rpp_orchestrator.component_storage import LinkedComponentRecord, ComponentRecord
from rpp_orchestrator.gui.new_script_dialog import NewScriptDialog

from rpp_plugin_registrator.library_manager import LibraryManager

from .assign_or_create_component_dialog import create_assign_or_create_component_dialog
from ..vscode_debug_config_service import VscodeDebugConfigService
from ..workspace import Workspace, default_script_source
from rpp_plugin_registrator.plugin_type_registrator import get_plugin_types
from ..script_handle import ScriptHandle


def _open_in_system_editor(path: Path) -> None:
    code_cmd = shutil.which("code")
    if code_cmd:
        subprocess.Popen([code_cmd, str(path)])
        return

    xdg_open = shutil.which("xdg-open")
    if xdg_open:
        subprocess.Popen([xdg_open, str(path)])
        return

    raise RuntimeError("No suitable editor launcher found. Install VS Code or xdg-open.")


def _open_in_file_explorer(path: Path) -> None:
    file_managers = ["nautilus", "dolphin", "nemo", "thunar", "pcmanfm"]
    for manager in file_managers:
        cmd = shutil.which(manager)
        if cmd:
            subprocess.Popen([cmd, str(path)])
            return

    xdg_open = shutil.which("xdg-open")
    if xdg_open:
        subprocess.Popen([xdg_open, str(path)])
        return

    raise RuntimeError("No suitable file manager launcher found. Install a file manager or xdg-open.")

class WorkspaceEditor(QWidget):


    COMPONENT_COLORS = {
        "component_key": QColor("#CACACA"),
        "component_instance": QColor("#D9EEFF"),
        "linked_component_ok": QColor("#D9FFD9"),
        "linked_component_failed": QColor("#FFCCCC"),

        "plugin_type": QColor("#F3F3F3"),
    }


    def eventFilter(self, source, event):
        if event.type() != event.Type.MouseButtonPress:
            return False
        if source == self.script_part_tree.viewport():
            tree_widget = self.script_part_tree
        else:
            tree_widget = self.workspace_components_tree
        click_position = event.position().toPoint()
        item = tree_widget.itemAt(click_position)

        if item is None:
            self._on_no_item_clicked()
            tree_widget.clearSelection()
            tree_widget.setCurrentItem(None)

        return super().eventFilter(source, event)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.lib_manager = LibraryManager()
        self.vscode_debug_config_service = VscodeDebugConfigService()
        self.workspace: Workspace | None = None
        self.current_script_handle: ScriptHandle | None = None
        self.current_part_id: str = ""
        self.current_part_saved_name: str = ""
        self.current_part_source: str = ""
        self.current_part_node_path: tuple[object, ...] = ()

        self.script_list = QListWidget(self)
        self.script_list.currentItemChanged.connect(self._on_script_changed)
        self.script_list.itemDoubleClicked.connect(self.open_selected_script)
        self.script_list.setMinimumWidth(220)
        self.script_list.setMaximumWidth(700)

        self.workspace_components_label = QLabel("Workspace Components", self)
        self.workspace_components_tree = QTreeWidget(self)
        self.workspace_components_tree.setHeaderLabels(["Component"])
        self.workspace_components_tree.setMinimumWidth(300)
        self.workspace_components_tree.setColumnWidth(0, 360)
        self.workspace_components_tree.itemClicked.connect(
            self._on_workspace_component_clicked)

        self.workspace_components_tree.itemDoubleClicked \
            .connect(self._on_workspace_part_tree_double_clicked)
        self.workspace_components_tree.viewport() \
                .installEventFilter(self)


        self.script_part_tree = QTreeWidget(self)
        self.script_part_tree.setHeaderLabels(["Component"])
        self.script_part_tree.itemClicked.connect(self._on_script_part_tree_clicked)
        self.script_part_tree.viewport() \
                .installEventFilter(self)

        self.script_part_tree.setMinimumWidth(300)
        self.script_part_tree.setMaximumWidth(700)
        self.script_part_tree.setColumnWidth(0, 200)

        self.part_title = QLabel("No component selected", self)
        self.part_title.setObjectName("componentTitle")

        self.part_name_editor = QLineEdit(self)
        self.part_name_editor.setEnabled(False)
        self.part_name_editor.setMaximumWidth(260)
        self.part_name_editor.textChanged.connect(self._on_part_name_text_changed)

        self.part_path_label = QLabel("", self)
        self.part_path_label.setWordWrap(True)
        self.part_path_label.setVisible(False)

        self.part_plugin_label = QLabel("Plugin: ", self)
        self.part_plugin_label.setWordWrap(False)

        self.part_library_label = QLabel("Library: ", self)
        self.part_library_label.setWordWrap(False)

        self.part_plugin_library_row = QWidget(self)
        self.part_plugin_library_row_layout = QHBoxLayout(self.part_plugin_library_row)
        self.part_plugin_library_row_layout.setContentsMargins(0, 0, 0, 0)
        self.part_plugin_library_row_layout.setSpacing(8)
        self.part_plugin_library_row_layout.addWidget(self.part_plugin_label)
        self.part_plugin_library_row_layout.addWidget(self.part_library_label)
        self.part_plugin_library_row_layout.addStretch(1)

        self.part_open_params_button = QPushButton("Open Parameter File", self)
        self.part_open_params_button.clicked.connect(self.open_selected_part_parameters)
        self.part_open_params_button.setEnabled(False)

        self.part_open_context_button = QPushButton("Open Component Context", self)
        self.part_open_context_button.clicked.connect(self.open_selected_part_context)
        self.part_open_context_button.setEnabled(False)

        self.part_open_plugin_manager_button = QPushButton("Open Plugin Manager", self)
        self.part_open_plugin_manager_button.clicked.connect(self.open_plugin_manager)
        self.part_open_plugin_manager_button.setEnabled(True)

        self.part_refresh_plugins = QPushButton("Refresh Plugins", self)
        self.part_refresh_plugins.clicked.connect(self._refresh_plugins)
        self.part_refresh_plugins.setEnabled(True)

        self.part_save_name_button = QPushButton("Save Description", self)
        self.part_save_name_button.clicked.connect(self.save_selected_part_description)
        self.part_save_name_button.setEnabled(False)

        self.add_component_button = QPushButton("Add Component", self)
        self.add_component_button.clicked.connect(self.open_add_component_dialog)
        self.add_component_button.setEnabled(False)

        self.remove_component_button = QPushButton("Remove Component", self)
        self.remove_component_button.clicked.connect(self.remove_selected_component)
        self.remove_component_button.setEnabled(False)

        self.duplicate_component_button = QPushButton("Duplicate Component", self)
        self.duplicate_component_button.clicked.connect(self.duplicate_selected_component)
        self.duplicate_component_button.setEnabled(False)

        self.debug_script_button = QPushButton("Debug Script", self)
        self.debug_script_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation))
        self.debug_script_button.clicked.connect(self.debug_selected_script)
        self.debug_script_button.setEnabled(False)

        self.new_script_button = QPushButton("New Script", self)
        self.new_script_button.clicked.connect(self.create_script)
        self.new_script_button.setEnabled(False)

        self.load_script_button = QPushButton("Load Script", self)
        self.load_script_button.clicked.connect(self.load_script)
        self.load_script_button.setEnabled(False)

        self.delete_script_button = QPushButton("Delete Script", self)
        self.delete_script_button.clicked.connect(self.delete_selected_script)
        self.delete_script_button.setEnabled(False)

        self.refresh_scripts_button = QPushButton("Refresh Scripts", self)
        self.refresh_scripts_button.clicked.connect(self.refresh_scripts_view)
        self.refresh_scripts_button.setEnabled(False)

        self.open_context_button = QPushButton("Open context", self)
        self.open_context_button.clicked.connect(self.open_workspace_context)
        self.open_context_button.setEnabled(False)

        self.help_label = QLabel("Double-click a script to open it in your editor.", self)
        self.help_label.setObjectName("helpLabel")

        self.log_textbox = QPlainTextEdit(self)
        self.log_textbox.setReadOnly(True)
        self.log_textbox.setMinimumHeight(120)

        script_actions = QWidget(self)
        script_actions_layout = QVBoxLayout(script_actions)
        script_actions_layout.setContentsMargins(0, 0, 0, 0)
        script_actions_layout.setSpacing(8)
        script_actions_layout.addWidget(self.help_label)
        script_actions_layout.addWidget(self.new_script_button)
        script_actions_layout.addWidget(self.load_script_button)
        script_actions_layout.addWidget(self.refresh_scripts_button)
        script_actions_layout.addWidget(self.delete_script_button)
        script_actions_layout.addWidget(self.open_context_button)
        script_actions_layout.addWidget(self.part_open_plugin_manager_button)
        script_actions_layout.addWidget(self.part_refresh_plugins)

        script_panel = QWidget(self)
        script_panel_layout = QVBoxLayout(script_panel)
        script_panel_layout.setContentsMargins(0, 0, 0, 0)
        script_panel_layout.setSpacing(8)
        script_panel_layout.addWidget(self.script_list, 2)
        script_panel_layout.addWidget(self.workspace_components_label)
        script_panel_layout.addWidget(self.script_part_tree, 2)
        script_panel_layout.addWidget(script_actions, 2)
        script_panel.setMaximumWidth(500)

        part_details = QWidget(self)
        part_details_layout = QFormLayout(part_details)
        part_details_layout.setContentsMargins(0, 0, 0, 0)
        part_details_layout.setSpacing(10)
        part_details_layout.addRow("Name", self.part_name_editor)
        part_details_layout.addRow(self.part_plugin_library_row)

        part_actions = QWidget(self)
        part_actions_layout = QVBoxLayout(part_actions)
        part_actions_layout.setContentsMargins(0, 0, 0, 0)
        part_actions_layout.setSpacing(6)

        part_actions_row_1 = QWidget(self)
        part_actions_row_1_layout = QHBoxLayout(part_actions_row_1)
        part_actions_row_1_layout.setContentsMargins(0, 0, 0, 0)
        part_actions_row_1_layout.setSpacing(10)
        part_actions_row_1_layout.addWidget(self.add_component_button)
        part_actions_row_1_layout.addWidget(self.remove_component_button)
        part_actions_row_1_layout.addWidget(self.duplicate_component_button)
        part_actions_row_1_layout.addStretch(1)

        part_actions_row_2 = QWidget(self)
        part_actions_row_2_layout = QHBoxLayout(part_actions_row_2)
        part_actions_row_2_layout.setContentsMargins(0, 0, 0, 0)
        part_actions_row_2_layout.setSpacing(10)
        part_actions_row_2_layout.addWidget(self.part_open_params_button)
        part_actions_row_2_layout.addWidget(self.part_open_context_button)
        part_actions_row_2_layout.addWidget(self.part_save_name_button)
        part_actions_row_2_layout.addStretch(1)

        part_actions_row_3 = QWidget(self)
        part_actions_row_3_layout = QHBoxLayout(part_actions_row_3)
        part_actions_row_3_layout.setContentsMargins(0, 0, 0, 0)
        part_actions_row_3_layout.setSpacing(10)
        part_actions_row_3_layout.addWidget(self.debug_script_button)
        part_actions_row_3_layout.addStretch(1)

        part_actions_layout.addWidget(part_actions_row_1)
        part_actions_layout.addWidget(part_actions_row_2)
        part_actions_layout.addWidget(part_actions_row_3)

        part_panel = QWidget(self)
        part_panel_layout = QVBoxLayout(part_panel)
        part_panel_layout.setContentsMargins(0, 0, 0, 0)
        part_panel_layout.setSpacing(8)
        part_panel_layout.addWidget(self.part_title)
        part_panel_layout.addWidget(self.workspace_components_tree, 3)
        part_panel_layout.addWidget(part_details)
        part_panel_layout.addWidget(part_actions)
        part_panel_layout.addWidget(self.log_textbox)

        body = QWidget(self)
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(14)
        body_layout.addWidget(script_panel, 1)
        body_layout.addWidget(part_panel, 2)
        # Set script panel to be 40% of the width and part panel to be 60% of the width
        body_layout.setStretch(0, 2)
        body_layout.setStretch(1, 3)

        layout = QVBoxLayout(self)
        layout.addWidget(body)

        self.plugin_types: dict[str, dict[str, Any]] = {}
        self.available_plugins: dict[str, dict[str, list[dict[str, Any]]]] = {}
        self.workspace_components: dict[str, list[ComponentRecord]] = {}
        self._load_plugin_types()
        self._load_plugins()

    def open_plugin_manager(self) -> None:
        if self.workspace is None:
            return
        try:
            from rpp_plugin_registrator.gui import RPPPluginManager
            plugin_manager = RPPPluginManager(self.lib_manager, parent=self)
            plugin_manager.show()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open plugin manager: {e}")

    def set_workspace(self, workspace: Workspace) -> None:
        self.workspace = workspace
        self.current_script_handle = None
        self.new_script_button.setEnabled(True)
        self.load_script_button.setEnabled(True)
        self.refresh_scripts_button.setEnabled(True)
        self.delete_script_button.setEnabled(True)
        self.open_context_button.setEnabled(True)
        self.refresh_scripts()
        self._refresh_workspace_components_tree()
        self._refresh_parts_from_script(self.current_script_handle)
        self._reset_part_views()
        self._update_script_management_buttons()

    def refresh_scripts_view(self) -> None:
        previous_script = self.current_script_handle
        self.refresh_scripts()

        if previous_script is not None:
            self._select_script_path(previous_script)

        current_item = self.script_list.currentItem()
        if current_item is not None:
            self._on_script_changed(current_item, None)
        else:
            self.current_script_handle = None
            self._refresh_parts_from_script(self.current_script_handle)
            self._reset_part_views()

        self._refresh_workspace_components_tree()

    def refresh_scripts(self) -> None:
        self.script_list.clear()
        if self.workspace is None:
            return
        for script_h in self.workspace.list_scripts():
            script_path = script_h.path
            self.workspace.ensure_script_assignments(script_path)
            item = QListWidgetItem(script_path.name)
            item.setData(Qt.ItemDataRole.UserRole, str(script_path))
            self.script_list.addItem(item)

    def _refresh_workspace_components_tree(self) -> None:
        self.workspace_components_tree.clear()

        grouped_records: dict[str, list[ComponentRecord]] = {}
        for record in self.workspace.iterate_part_records(root_only=True):
            grouped_records.setdefault(record.plugin_type, []).append(record)

        self.workspace_components = grouped_records

        for category in sorted(grouped_records.keys()):
            category_item = QTreeWidgetItem([category])
            category_item.setData(
                0, Qt.ItemDataRole.UserRole,
                {
                    "plugin_type": category,
                    "component_key": None,
                    "root": True,
                    "node_path": (category,),
                }
            )
            category_item.setBackground(0,
                self.COMPONENT_COLORS.get("plugin_type", "#FFFFFF"))
            category_item.setFirstColumnSpanned(True)
            self.workspace_components_tree.addTopLevelItem(category_item)
            for record in sorted(grouped_records[category], key=lambda item: item.name):
                self._add_part_record_item(category, record, category_item)
            category_item.setExpanded(True)

    def _on_script_changed(self, current: QListWidgetItem | None, previous: QListWidgetItem | None) -> None:
        del previous
        if self.workspace is None or current is None:
            self.current_script_handle = None
            self._update_script_management_buttons()
            return

        script_path = Path(current.data(Qt.ItemDataRole.UserRole))
        script_handle = ScriptHandle(script_path, self.workspace)
        self.current_script_handle = script_handle
        self._refresh_parts_from_script(script_handle)
        self._update_script_management_buttons()

    def _refresh_parts_from_script(self, script_handle: ScriptHandle) -> None:
        self.script_part_tree.clear()
        if script_handle is None or self.workspace is None:
            return

        components = script_handle.slots
        if not components:
            return

        records_by_component_key: dict[str, list[ComponentRecord]] = {}
        assignments = script_handle.load_description()

        records_by_id = self.workspace.part_records
        for component_key, items in assignments["Components"].items():
            assigned_records = []
            if not isinstance(items, list):
                items = [items]
            for item in items:
                component_id = item.get("Id")
                record = records_by_id.get(str(component_id))
                if record is not None:
                    assigned_records.append(record)
            if assigned_records:
                records_by_component_key[str(component_key)] = assigned_records

        components_item = QTreeWidgetItem(["COMPONENTS"])
        components_item.setData(0, Qt.ItemDataRole.UserRole, {"script_slot": False, "is_root": True})
        components_item.setFirstColumnSpanned(True)
        self.script_part_tree.addTopLevelItem(components_item)

        for key, value in components.items():
            try:
                type_info = self.get_plugin_type_info(value)
            except Exception:
                self.log_textbox.appendPlainText(f"Warning: Could not load plugin info for {value}.")
                continue
            item = QTreeWidgetItem([f"{key} ({value})"])
            item.setData(
                0,
                Qt.ItemDataRole.UserRole,
                {
                    "script_slot": True,
                    "type_info": type_info,
                    "script_path": str(script_handle.path),
                    "node_path": (key,),
                    "slot_name": str(key),
                }
            )
            components_item.addChild(item)

            for record in records_by_component_key.get(str(key), []):
                display_name = str(record.name or record.folder.name)
                option_item = QTreeWidgetItem([display_name])
                option_item.setData(
                    0,
                    Qt.ItemDataRole.UserRole,
                    {
                        "id": str(record.id),
                        "existing_component": True,
                        "folder": str(record.folder),
                        "option_count": len(records_by_component_key.get(str(key), [])),
                        "node_path": (key, record.id),
                        "record": record,
                    },
                )
                item.addChild(option_item)

            item.setExpanded(True)

        components_item.setExpanded(True)


    def _add_part_record_item(self,
            category: str, record: ComponentRecord,
            parent: QTreeWidgetItem) -> None:
        display_name = f"{record.name} ({record.plugin_name})"
        item = QTreeWidgetItem([display_name])
        item.setData(
            0,
            Qt.ItemDataRole.UserRole,
            {
                "folder": str(record.folder),
                "node_path": (category, record.id),
                "record": record,
                "id": str(record.id),
            },
        )

        item.setBackground(0,
            self.COMPONENT_COLORS.get("component_instance", "#FFFFFF"))
        parent.addChild(item)
        self._populate_component_children(item, record, (category, record.id))

    def _populate_component_children(
        self,
        parent_item: QTreeWidgetItem,
        record: ComponentRecord | LinkedComponentRecord,
        node_path: tuple[object, ...],
    ) -> None:
        if isinstance(record, LinkedComponentRecord):
            # For linked components, we don't populate children since they are not stored in the workspace.
            return
        subcomponents = record.subcomponents or {}
        subcomponent_spec = record.subcomponent_spec or {}

        specs = {}
        for key in subcomponent_spec:
            plugin_type = record.subcomponent_spec[key]
            child_item = QTreeWidgetItem([f"{key} ({plugin_type})"])
            path = node_path + (key,)
            child_item.setData(
                0,
                Qt.ItemDataRole.UserRole,
                {
                    "id": str(path),
                    "node_path": path,
                    "plugin_type": plugin_type,
                    "parent_component_id": str(record.id),
                    "component_key": str(key),
                    "subcomponent_spec": True,
                },
            )
            specs[key] = child_item
            child_item.setBackground(0,
                self.COMPONENT_COLORS.get("component_key", "#FFFFFF"))
            parent_item.addChild(child_item)

        for key, value in subcomponents.items():
            spec_item = specs.get(key)
            assert spec_item is not None, f"Spec item for key '{key}' not found."

            subcomponent_record = self.workspace.get_subcomponent(record.id, key)
            child_node_path = node_path + (key,)

            if isinstance(subcomponent_record, LinkedComponentRecord):
                instance_color = self.COMPONENT_COLORS.get("linked_component_ok", "#FFFFFF")
                if not self.workspace.is_linked_component_valid(subcomponent_record):
                    instance_color = self.COMPONENT_COLORS.get("linked_component_failed", "#FFFFFF")
            else:
                instance_color = self.COMPONENT_COLORS.get("component_instance", "#FFFFFF")

            if subcomponent_record is None:
                continue
            elif isinstance(value, list):
                assert isinstance(subcomponent_record, list)
                for idx, sub_value in enumerate(value):
                    name = str(subcomponent_record[idx].name)
                    child_item = QTreeWidgetItem([self._display_value(name)])
                    child_item.setData(
                        0,
                        Qt.ItemDataRole.UserRole,
                        {
                            "folder": str(record.folder),
                            "node_path": child_node_path + (subcomponent_record[idx].id,),
                            "component_key": str(key),
                            "record": subcomponent_record[idx],
                            "subcomponent_spec": False,
                            "id": str(subcomponent_record[idx].id),
                        },
                    )
                    child_item.setBackground(0, instance_color)
                    spec_item.addChild(child_item)
                    self._populate_component_children(child_item,
                            subcomponent_record[idx], node_path + (key, idx))
            else:
                name = str(subcomponent_record.name)
                child_item = QTreeWidgetItem([self._display_value(name)])
                child_item.setData(
                    0,
                    Qt.ItemDataRole.UserRole,
                    {
                        "folder": str(record.folder),
                        "node_path": child_node_path + (subcomponent_record.id,),
                        "record": subcomponent_record,
                        "component_key": str(key),
                        "subcomponent_spec": False,
                        "id": str(subcomponent_record.id),
                    },
                )
                child_item.setBackground(0, instance_color)
                spec_item.addChild(child_item)
                self._populate_component_children(child_item,
                        subcomponent_record, node_path + (key,))

    def _display_value(self, value: object) -> str:
        if isinstance(value, dict):
            return "{...}"
        if isinstance(value, list):
            return f"[{len(value)} items]"
        return str(value)


    def _on_workspace_component_changed(self, current: QTreeWidgetItem | None, previous: QTreeWidgetItem | None) -> None:
        if current is None:
            self._reset_part_views()
            return

        payload = current.data(0, Qt.ItemDataRole.UserRole)

        if self.workspace is None:
            self._reset_part_views()
            return

        if "root" in payload and payload["root"] is True:
            self._reset_part_views()
            return

        if "subcomponent_spec" in payload and payload["subcomponent_spec"] is True:
            # Handle subcomponent spec selection
            if current.childCount() > 0:
                self.add_component_button.setText("Override Subcomponent")
            else:
                self.add_component_button.setText("Add Subcomponent")
            self.add_component_button.setEnabled(True)
            self.remove_component_button.setEnabled(False)
            self.duplicate_component_button.setEnabled(False)
            self.part_open_params_button.setEnabled(False)
            self.part_open_context_button.setEnabled(False)
            self.part_save_name_button.setEnabled(False)
            self.part_name_editor.setEnabled(False)
            self.current_part_id = None
            self.part_name_editor.setText(payload.get("component_key", ""))
            self.part_plugin_label.setText(f"Plugin: {payload.get('plugin_type', '')}")
            self.part_library_label.setText("Library: -")
            return

        folder = Path(payload["record"].folder)
        try:
            record = self.workspace.read_part_descriptor(folder)
            plugin_name, plugin_type, library = \
                self.resolve_info_from_component_record(record)
        except FileNotFoundError:
            self._reset_part_views()
            return

        self.current_part_id = record.id
        self.current_part_node_path = payload.get("node_path", ())
        self.current_part_source = "workspace"
        self.current_part_saved_name = record.name
        self.part_title.setText(f"{self.current_part_saved_name} ({plugin_type})")
        self.part_path_label.setText(str(folder))
        self.part_name_editor.setEnabled(True)
        self.part_name_editor.setText(self.current_part_saved_name)
        self.part_plugin_label.setText(f"Plugin: {str(plugin_name or '')}")
        self.part_library_label.setText(
            f"Library: {str(library or '-') }"
        )
        self.add_component_button.setEnabled(False)
        self.remove_component_button.setEnabled(True)
        self.remove_component_button.setText("Remove Component")
        self.part_open_params_button.setEnabled(True)
        self.part_open_context_button.setEnabled(True)
        if isinstance(record, LinkedComponentRecord):
            self.duplicate_component_button.setEnabled(False)
            self.part_save_name_button.setEnabled(False)
        else:
            self.duplicate_component_button.setEnabled(True)
            self.part_save_name_button.setEnabled(True)

    def _on_script_part_tree_changed(self, current: QTreeWidgetItem | None, previous: QTreeWidgetItem | None) -> None:
        #del previous
        if current is None:
            self._reset_part_views()
            return



        context = current.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(context, dict):
            self._reset_part_views()
            return


        self.current_part_node_path = context.get("node_path", ())
        option_count = int(context.get("option_count", 0))
        self.add_component_button.setText("Add Option" if option_count > 0 else "Add Component")
        self.remove_component_button.setText("Remove Option" if option_count > 0 else "Remove Component")

        # Handle script-assigned component selection
        if context.get("script_slot") is True:
            info = context.get("type_info")
            if info is None:
                self.log_message("Error: Plugin type info not found for the selected component.")
                return
            name = info["Name"]
            class_name = info["ClassName"]
            lib_name = info["Library"]
            self.current_part_source = None
            self.current_part_saved_name = name
            self.part_title.setText(f"{name} ({class_name})")
            self.part_path_label.setText(str(context.get("script_path", "")))
            self.part_name_editor.setText(name)
            self.part_name_editor.setEnabled(False)
            self.part_plugin_label.setText(f"Plugin: {class_name}")
            self.part_library_label.setText(f"Library: {lib_name}")
            self.add_component_button.setEnabled(True)

            self.remove_component_button.setEnabled(False)
            self.duplicate_component_button.setEnabled(False)
            self.part_open_params_button.setEnabled(False)
            self.part_open_context_button.setEnabled(False)
            self.part_save_name_button.setEnabled(True)
            return

        if "folder" not in context:
            self._reset_part_views()
            return


        folder = Path(context["folder"])

        if self.workspace is None:
            self._reset_part_views()
            return

        try:
            descriptor = self.workspace.read_part_descriptor(folder)
            plugin_name, plugin_type, library = \
                self.resolve_info_from_component_record(descriptor)
        except FileNotFoundError:
            self._reset_part_views()
            return

        self.current_part_id = descriptor.id
        self.current_part_source = "script"
        self.current_part_saved_name = descriptor.name
        self.part_title.setText(context["record"].name)
        self.part_path_label.setText(str(folder))
        self.part_name_editor.setEnabled(True)
        self.part_name_editor.setText(descriptor.name)
        self.part_plugin_label.setText(f"Plugin: {str(plugin_name or '')}")
        self.part_library_label.setText(f"Library: {str(library or '-') }")
        self.add_component_button.setEnabled(False)
        self.remove_component_button.setEnabled(True)
        self.duplicate_component_button.setEnabled(False)  # Disable duplication for script componentss
        self.part_open_params_button.setEnabled(True)
        self.part_open_context_button.setEnabled(True)
        self.part_save_name_button.setEnabled(True)

    def resolve_info_from_component_record(self,
            record: ComponentRecord | LinkedComponentRecord) -> tuple[str, str, str]:
        if isinstance(record, LinkedComponentRecord):
            linked = self.workspace.get_linked_component(record)
            if linked is None:
                raise ValueError(f"Linked component with ID {record.id} not found.")
            return linked.plugin_name, linked.plugin_type, linked.library
        return record.plugin_name, record.plugin_type, record.library

    def _on_script_part_tree_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        del column
        # Keep selection mutually exclusive between script component tree and workspace component tree.
        with QSignalBlocker(self.workspace_components_tree):
            self.workspace_components_tree.setCurrentItem(None)

        # Update details once. currentItemChanged will handle non-current clicks.
        self._on_script_part_tree_changed(item, None)


    def _on_no_item_clicked(self):
        self._reset_part_views()

    def _on_workspace_component_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        del column
        # Keep selection mutually exclusive between script component tree and workspace component tree.
        with QSignalBlocker(self.script_part_tree):
            self.script_part_tree.setCurrentItem(None)

        self._on_workspace_component_changed(item, None)

    def _on_workspace_part_tree_double_clicked(self,
            item: QTreeWidgetItem, column: int) -> None:
        del column
        context = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(context, dict):
            return

        if "record" not in context:
            return

        record : ComponentRecord | LinkedComponentRecord = context["record"]
        plugin_name, plugin_type, library = \
            self.resolve_info_from_component_record(record)
        # Ensure plugin type info is loaded
        info = self.get_plugin_info(plugin_name, plugin_type, library)

        file_path = self.lib_manager.get_plugin_path_absolute(
            info["SourceFile"], library)

        _open_in_system_editor(file_path)

    def _selected_script_component_kv(self) -> tuple[str, str]:
        item = self.script_part_tree.currentItem()
        while item is not None:
            context = item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(context, dict) \
                    and context.get("script_slot") is True:
                info = context.get("type_info", {})
                return (context.get("slot_name", ""), \
                        info.get("PluginTypeName", ""))
            item = item.parent()
        return "", ""

    def _get_node_path_for_current_part(self) \
            -> tuple[object, ...]:
        return self.current_part_node_path

    def _node_at_path(self,
            payload: object, node_path: tuple[object, ...]) -> object:
        node = payload
        for step in node_path:
            if isinstance(node, dict) and isinstance(step, str):
                node = node.get(step)
            elif isinstance(node, list) and isinstance(step, int) \
                    and 0 <= step < len(node):
                node = node[step]
            else:
                return {}
        return node

    def open_selected_part_parameters(self) -> None:
        current_part_folder = self.workspace \
            .resolve_linked_folder(self.current_part_id)
        params_path = self.workspace.component_parameter_store\
            .ensure_parameters_file(current_part_folder)
        try:
            _open_in_system_editor(params_path)
        except Exception as exc:
            QMessageBox.critical(self, "Open parameters failed", str(exc))

    def open_selected_part_context(self) -> None:
        current_part_folder = self.workspace \
            .get_component(self.current_part_id).folder
        if current_part_folder is None:
            return
        try:
            _open_in_file_explorer(current_part_folder)
        except Exception as exc:
            QMessageBox.critical(self, "Open component context failed", str(exc))

    def save_selected_part_description(self) -> None:
        component = self.workspace.get_component(self.current_part_id)
        current_part_folder = component.folder
        if self.workspace is None or current_part_folder is None:
            return

        try:
            record : ComponentRecord = \
                self.workspace.read_part_descriptor(current_part_folder)
        except FileNotFoundError as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return

        new_name = self.part_name_editor.text().strip()
        if not new_name:
            QMessageBox.information(self,
                "Save description", "Name cannot be empty.")
            return

        # Create a new record with the updated name
        updated_record = ComponentRecord(
            id=record.id,
            name=new_name,
            plugin_type=record.plugin_type,
            plugin_name=record.plugin_name,
            library=record.library,
            subcomponent_spec=record.subcomponent_spec,
            folder=record.folder,
        )
        self.workspace.write_part_descriptor(
            updated_record.folder, updated_record)
        self.current_part_saved_name = new_name
        self.log_message(f"Saved description.json for {new_name}")
        changed = self._update_active_component_name(
            new_name, self.current_part_source, dirty=False)
        if changed:
            self._refresh_part_title(new_name, is_dirty=False)

        path = self._get_node_path_for_current_part()
        self._refresh_current_script_parts()
        self._reselect_workspace_part_node(path)


    def _search_tree_for_part_id_recursive(self,
            tree: QTreeWidget, part_id: str) -> QTreeWidgetItem | None:
        root = tree.invisibleRootItem()
        stack = [root]
        while stack:
            current_item = stack.pop()
            for index in range(current_item.childCount()):
                child_item = current_item.child(index)
                payload = child_item.data(0, Qt.ItemDataRole.UserRole)
                if isinstance(payload, dict) and payload.get("id") == part_id:
                    return child_item
                if child_item.childCount() > 0:
                    stack.append(child_item)
        return None

    def _update_active_component_name(self,
            new_name: str,
            current_part_source: str | None, *, dirty: bool) -> None:

        def update_item_label(item: QTreeWidgetItem) -> bool:
            if item is None:
                return False
            context = item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(context, dict):
                label = f"{new_name} *" if dirty else new_name
                item.setText(0, label)
                context["name"] = new_name
                item.setData(0, Qt.ItemDataRole.UserRole, context)
                return True
            return False

        def get_item_from_part_tree(part_id):
            return self._search_tree_for_part_id_recursive(
                self.script_part_tree, part_id)

        def get_item_from_workspace_tree(part_id):
            return self._search_tree_for_part_id_recursive(
                self.workspace_components_tree, part_id)


        if current_part_source == "script":
            current_tree_item = self.script_part_tree.currentItem()
            if current_tree_item is not None \
                    and not self._allows_name_editing(current_tree_item):
                return False
            # find by component id
            current_workspace_item = get_item_from_workspace_tree(self.current_part_id)
        elif current_part_source == "workspace":
            current_workspace_item = self.workspace_components_tree.currentItem()
            if current_workspace_item is not None \
                    and not self._allows_name_editing(current_workspace_item):
                return False
            # find by component id
            current_tree_item = get_item_from_part_tree(self.current_part_id)
        else:
            return False

        update_item_label(current_tree_item)
        update_item_label(current_workspace_item)

        return True

    def _allows_name_editing(self, item: QTreeWidgetItem) -> bool:
        context = item.data(0, Qt.ItemDataRole.UserRole)
        if "descriptor_path" in context:
            return True
        return False


    def _refresh_part_title(self, stripped_name: str, is_dirty: bool) -> None:
        comp = self.workspace.get_component(self.current_part_id)
        plugin_name, _, _ = self.resolve_info_from_component_record(comp)
        title_name = f"{stripped_name} *" if is_dirty else stripped_name
        self.part_title.setText(f"{title_name} ({plugin_name})")

    def _on_part_name_text_changed(self, new_name: str) -> None:
        # Always allow live update for both script and workspace components
        if self.current_part_id is None or self.workspace is None:
            return

        stripped_name = new_name.strip()
        is_dirty = stripped_name != self.current_part_saved_name
        changed = self._update_active_component_name(stripped_name,
                self.current_part_source, dirty=is_dirty)
        if changed:
            self._refresh_part_title(stripped_name, is_dirty)

    def _reselect_workspace_part_node(self,
            node_path: tuple[object, ...]) -> None:
        def matches(item: QTreeWidgetItem) -> bool:
            context = item.data(0, Qt.ItemDataRole.UserRole)
            return isinstance(context, dict) and \
                context.get("node_path", ()) == node_path

        def walk(item: QTreeWidgetItem) -> QTreeWidgetItem | None:
            if matches(item):
                return item
            for index in range(item.childCount()):
                result = walk(item.child(index))
                if result is not None:
                    return result
            return None

        for index in range(self.workspace_components_tree.topLevelItemCount()):
            item = walk(self.workspace_components_tree.topLevelItem(index))
            if item is not None:
                self.workspace_components_tree.setCurrentItem(item)
                item.setExpanded(True)
                self.workspace_components_tree.itemClicked.emit(item, 0)
                self.current_part_node_path = node_path
                break

    def _reset_part_views(self, clear_tree: bool = False) -> None:
        self.current_part_id = None
        self.current_part_saved_name = ""
        if clear_tree:
            self.script_part_tree.clear()
        self.part_title.setText("No component selected")
        self.part_name_editor.clear()
        self.part_name_editor.setEnabled(False)
        self.part_path_label.setText("")
        self.part_plugin_label.setText("Plugin: -")
        self.part_library_label.setText("Library: -")
        self.add_component_button.setEnabled(True)
        self.add_component_button.setText("Add Component")
        self.remove_component_button.setEnabled(False)
        self.duplicate_component_button.setEnabled(False)
        self.part_open_params_button.setEnabled(False)
        self.part_open_context_button.setEnabled(False)
        self.part_save_name_button.setEnabled(False)

    def _update_script_management_buttons(self) -> None:
        has_script = self.current_script_handle is not None
        self.debug_script_button.setEnabled(has_script)

    def debug_selected_script(self) -> None:
        if self.current_script_handle is None:
            QMessageBox.information(self,
                "Script", "Select a script first.")
            return

        workspace_root = self.workspace.root
        result = self.vscode_debug_config_service \
            .ensure_for_script(self.current_script_handle.path, workspace_root)
        if result.message:
            self.log_message(result.message)
        if result.status == "invalid":
            QMessageBox.critical(self,
                "Script", result.message \
                    or "Invalid VS Code debug configuration.")
            return

        launch_result = self.vscode_debug_config_service \
            .launch_debug_for_script(self.current_script_handle.path, workspace_root)
        if launch_result.message:
            self.log_message(launch_result.message)
        if launch_result.status != "ok":
            QMessageBox.critical(self,
                "Script", launch_result.message \
                    or "Failed to start VS Code debug session.")

    def open_add_component_dialog(self) -> None:

        current_item = self.workspace_components_tree.currentItem()
        script_item = self.script_part_tree.currentItem()
        offer_assign = True
        if current_item is None and script_item is None:
            plugin_type = None
            assign_subcomponent = False
            parent_component_id = None
            offer_assign = False
            component_key = None
        elif current_item is not None:
            payload = current_item.data(0, Qt.ItemDataRole.UserRole)
            if "subcomponent_spec" in payload \
                    and payload["subcomponent_spec"] is True:
                plugin_type = payload.get("plugin_type", "")
                component_key = payload.get("component_key", None)
                assign_subcomponent = True
                parent_component_id = payload.get("parent_component_id", None)
            else:
                plugin_type = payload.get("plugin_type", "")
                component_key = payload.get("component_key", None)
                assign_subcomponent = False
                parent_component_id = None
                offer_assign = component_key is not None
        elif script_item is not None:
            payload = script_item.data(0, Qt.ItemDataRole.UserRole)
            plugin_type = payload.get("type_info", {}).get("PluginTypeName", "")
            component_key = payload.get("slot_name", None)
            parent_component_id = None
            assign_subcomponent = False
        else:
            self.log_message("No valid selection for Add Component.")
            return

        dialog = create_assign_or_create_component_dialog(
                self, self.workspace_components,
                self.available_plugins, plugin_type=plugin_type,
                offer_assign=offer_assign)
        if dialog is None or not dialog.has_plugins:
            self.log_message(
                "No compatible plugins found for Add Component.")
            QMessageBox.information(self,
                "Add Component", "No compatible plugins found.")
            return

        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected_item_type, plugin = dialog.get_selected_item()
            if assign_subcomponent is False:
                if selected_item_type == "component" and plugin is not None:
                    self._assign_component_to_script(
                        plugin, log_info=True, refresh_workspace=False)
                elif selected_item_type == "plugin" and plugin is not None:
                    self._create_selected_component(
                        plugin, component_key)
                else:
                    self.log_message(
                        "No component or plugin selected for Add Component.")
                    QMessageBox.information(self,
                        "Add Component", "No component or plugin selected.")
            else:
                if selected_item_type == "component" and plugin is not None:
                    self._assign_subcomponent(plugin, log_info=True)
                elif selected_item_type == "plugin" and plugin is not None:
                    self._create_selected_component(
                        plugin, component_key, parent_component_id)
                else:
                    self.log_message(
                        "No component or plugin selected for Add Subcomponent.")
                    QMessageBox.information(
                        self, "Add Subcomponent", "No component or plugin selected.")

    def log_message(self, message: str) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log_textbox.appendPlainText(f"[{timestamp}] {message}")


    def _assign_component_to_script(self, record: ComponentRecord,
                component_key: str | None = None,
                log_info=False, refresh_workspace=False) -> None:
        if component_key is None:
            component_key, _ = self._selected_script_component_kv()
        self.workspace.assign_component_to_script(
            self.current_script_handle, component_key, record.id)
        if log_info:
            self.log_message(
                f"Assigned component {record.name} to script slot {component_key}")
        if refresh_workspace:
            self._refresh_workspace_components_tree()
        self._refresh_current_script_parts()


    def _assign_subcomponent(self, plugin_info: ComponentRecord,
                log_info=False) -> None:
        current_item = self.workspace_components_tree.currentItem()
        if current_item is None:
            QMessageBox.warning(self,
                "Assign Subcomponent", "Select a parent component first.")
            return

        payload = current_item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(payload, dict) or \
                "parent_component_id" not in payload or "component_key" not in payload:
            QMessageBox.warning(self, "Assign Subcomponent",
                "Select a valid parent component first.")
            return

        parent_component_id = payload["parent_component_id"]
        component_key = payload["component_key"]

        parent_record, child_record = \
            self.workspace.assign_subcomponent_to_parent(
                parent_component_id, component_key, plugin_info.id)
        if log_info:
            self.log_message(f"Assigned subcomponent {child_record.name}"
                f" to parent component {parent_record.name} at slot {component_key}")
        path = self._get_node_path_for_current_part()
        self._refresh_workspace_components_tree()
        self._reselect_workspace_part_node(path + (child_record.id,))


    def _create_selected_component(self,
            plugin: dict[str, Any],
            component_key : str | None = None,
            parent_component_id : str | None = None) -> None:
        if parent_component_id is None:
            if self.workspace is None or self.current_script_handle is None:
                QMessageBox.warning(self,
                    "Add Component", "Select a script before adding a component.")
                return

        plugin_type = plugin["PluginType"]
        if not plugin_type:
            QMessageBox.warning(self, "Add Component",
                "The selected entry does not define a plugin type.")
            return

        component_name = f"{plugin['Name']}_comp"
        if parent_component_id is None:
            record = self.workspace.create_component(
                component_name=component_name,
                plugin_name=plugin["PluginName"],
            )
            if component_key is not None:
                self._assign_component_to_script(record,
                    component_key, log_info=False, refresh_workspace=False)
        else:
            parent_record = self.workspace.get_component(parent_component_id)
            if parent_record is None:
                self.log_message(f"Parent component with ID {parent_component_id} not found.")
                return
            assert component_key is not None, \
                "Component key must be provided when adding a subcomponent."

            record = self.workspace.create_subcomponent(
                parent_folder=parent_record.folder,
                slot_name=component_key,
                component_name=component_name,
                plugin_name=plugin["PluginName"]
            )

        self.log_message(f"Created component {component_name} at {record.folder}")
        self._refresh_current_script_parts()
        path = self._get_node_path_for_current_part()
        self._refresh_workspace_components_tree()
        self._reselect_workspace_part_node(path + (record.id,))

    def remove_selected_component(self) -> None:

        current_part_folder = self.workspace.get_component(self.current_part_id).folder
        if current_part_folder is None:
            return

        if QMessageBox.question(
            self, "Remove Component",
            "Remove selected component?") != QMessageBox.StandardButton.Yes:
            return

        try:
            if self.current_part_source == "script" \
                    and self.current_script_handle is not None:
                component_key, _ = self._selected_script_component_kv()
                self.workspace.remove_component_from_script(
                    self.current_script_handle, self.current_part_id, component_key)
            elif self.current_part_source == "workspace":
                self.workspace.remove_component(self.current_part_id)
            else:
                QMessageBox.warning(self,
                    "Remove Component",
                    "Cannot determine the source of the selected component.")
                return
            self.log_message(f"Removed component at {current_part_folder}")
        except Exception as exc:
            QMessageBox.critical(self,
                "Remove Component", f"Failed to remove component: {exc}")
            return

        self._refresh_current_script_parts()
        self._reset_part_views()
        path = self._get_node_path_for_current_part()
        self._refresh_workspace_components_tree()
        self._reselect_workspace_part_node(path[:-1])


    def duplicate_selected_component(self) -> None:
        current_part_folder = self.workspace.get_component(
            self.current_part_id).folder
        if current_part_folder is None:
            return

        try:
            if self.current_part_source == "script":
                return
            if self.current_part_source == "workspace":
                duplicated_record = \
                    self.workspace.duplicate_component(self.current_part_id)
                self.log_message(
                    f"Duplicated component to {duplicated_record.folder}")
        except Exception as exc:
            QMessageBox.critical(self,
                "Duplicate Component", f"Failed to duplicate component: {exc}")
            return

        self._refresh_current_script_parts()
        path = self._get_node_path_for_current_part()
        duplicated_path = path[:-1] + (duplicated_record.id,)
        self._refresh_workspace_components_tree()
        self._reselect_workspace_part_node(duplicated_path)

    def _refresh_current_script_parts(self) -> None:
        if self.current_script_handle is not None:
            self._refresh_parts_from_script(self.current_script_handle)


    def open_selected_script(self, item: QListWidgetItem | None = None) -> None:
        if self.workspace is None:
            return

        if item is None:
            item = self.script_list.currentItem()
            if item is None:
                return

        script_path = Path(item.data(Qt.ItemDataRole.UserRole))
        try:
            _open_in_system_editor(script_path)
        except Exception as exc:
            QMessageBox.critical(self, "Open script failed", str(exc))

    def create_script(self) -> None:
        if self.workspace is None:
            return

        dialog = NewScriptDialog(self, title="Create New Script")
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        script_name = dialog.name
        script_path = Path(dialog.path) / script_name
        script_handle = self.workspace.create_script(
            script_path, default_script_source(script_path))
        self.refresh_scripts()
        self._select_script_path(script_handle)
        self.open_selected_script(self.script_list.currentItem())

    def load_script(self) -> None:
        script_path, _ = QFileDialog.getOpenFileName(
            self, "Load Script", str(self.workspace.root), "All Files (*)")
        if not script_path:
            return
        script_handle = self.workspace.load_script(Path(script_path))
        self.refresh_scripts()
        self._select_script_path(script_handle)
        self.open_selected_script(self.script_list.currentItem())

    def delete_selected_script(self) -> None:
        if self.workspace is None:
            return
        item = self.script_list.currentItem()
        if item is None:
            return
        script_path = Path(item.data(Qt.ItemDataRole.UserRole))
        if QMessageBox.question(self,
            "Delete script", f"Delete {script_path.name}?") \
                != QMessageBox.StandardButton.Yes:
            return
        self.workspace.delete_script(script_path)
        self.refresh_scripts()

    def open_workspace_context(self) -> None:
        if self.workspace is None:
            return
        try:
            _open_in_file_explorer(self.workspace.root)
        except Exception as exc:
            QMessageBox.critical(self, "Open context failed", str(exc))

    def _select_script_path(self, script_handle: ScriptHandle) -> None:
        self.current_script_handle = script_handle
        for index in range(self.script_list.count()):
            item = self.script_list.item(index)
            if Path(item.data(Qt.ItemDataRole.UserRole)) == script_handle.path:
                self.script_list.setCurrentItem(item)
                return


    def get_plugin_type_info(self, plugin_name: str) \
        -> dict[str, Any] | None:
        return self.plugin_types.get(plugin_name)

    def get_plugin_info(self,
            plugin_name: str, plugin_type: str,
            library: str | None) -> dict[str, Any] | None:
        lib_plugins = self.available_plugins.get(library)
        if lib_plugins is None:
            return None
        plugins = lib_plugins.get(plugin_type)
        if plugins is None:
            return None
        return next((p for p in plugins if p["PluginName"] == plugin_name), None)

    def _load_plugin_types(self) -> None:
        self.plugin_types = get_plugin_types()

    def _load_plugins(self) -> None:
        self.available_plugins = self.lib_manager.get_available_plugins()

    def _refresh_plugins(self) -> None:
        self._load_plugin_types()
        self._load_plugins()
        self.log_message("Plugin types and available plugins refreshed.")

