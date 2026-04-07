from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
import json
import shutil as path_shutil
from typing import Any
from uuid import uuid4

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QLineEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .available_plugins_dialog import create_available_plugins_dialog
from ..workspace import Workspace, default_script_source, script_class_name_from_name
from rpp_plugin_registrator.plugin_type_registrator import get_plugin_types


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
    def __init__(self, parent=None):
        super().__init__(parent)
        self.workspace: Workspace | None = None
        self.current_script_path: Path | None = None
        self.current_part_folder: Path | None = None
        self.current_part_descriptor_path: Path | None = None
        self.current_part_node_path: tuple[object, ...] = ()
        self.current_part_descriptor: dict[str, object] = {}
        self.current_part_fully_qualified_class_name: str = ""
        self.current_part_name: str = ""

        self.script_list = QListWidget(self)
        self.script_list.currentItemChanged.connect(self._on_script_changed)
        self.script_list.itemDoubleClicked.connect(self.open_selected_script)
        self.script_list.setMinimumWidth(220)
        self.script_list.setMaximumWidth(300)

        self.part_tree = QTreeWidget(self)
        self.part_tree.setHeaderLabels(["Component", "Value"])
        self.part_tree.currentItemChanged.connect(self._on_part_tree_changed)
        self.part_tree.itemClicked.connect(self._on_part_tree_clicked)
        self.part_tree.setMinimumWidth(420)
        self.part_tree.setMaximumWidth(700)
        self.part_tree.setColumnWidth(0, 360)

        self.part_title = QLabel("No component selected", self)
        self.part_title.setObjectName("componentTitle")

        self.part_name_editor = QLineEdit(self)
        self.part_name_editor.setEnabled(False)
        self.part_name_editor.setMaximumWidth(260)

        self.part_path_label = QLabel("", self)
        self.part_path_label.setWordWrap(True)
        self.part_path_label.setVisible(False)

        self.part_plugin_label = QLabel("", self)
        self.part_plugin_label.setWordWrap(True)

        self.part_library_label = QLabel("", self)
        self.part_library_label.setWordWrap(True)

        self.part_open_params_button = QPushButton("Open Parameter File", self)
        self.part_open_params_button.clicked.connect(self.open_selected_part_parameters)
        self.part_open_params_button.setEnabled(False)

        self.part_open_context_button = QPushButton("Open Component Context", self)
        self.part_open_context_button.clicked.connect(self.open_selected_part_context)
        self.part_open_context_button.setEnabled(False)

        self.part_save_name_button = QPushButton("Save Name", self)
        self.part_save_name_button.clicked.connect(self.save_selected_part_name)
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

        self.new_script_button = QPushButton("New Script", self)
        self.new_script_button.clicked.connect(self.create_script)
        self.new_script_button.setEnabled(False)

        self.delete_script_button = QPushButton("Delete Script", self)
        self.delete_script_button.clicked.connect(self.delete_selected_script)
        self.delete_script_button.setEnabled(False)

        self.open_button = QPushButton("Open Script", self)
        self.open_button.clicked.connect(self.open_selected_script)
        self.open_button.setEnabled(False)

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
        script_actions_layout.addWidget(self.open_button)
        script_actions_layout.addWidget(self.refresh_scripts_button)
        script_actions_layout.addWidget(self.delete_script_button)
        script_actions_layout.addWidget(self.open_context_button)

        script_panel = QWidget(self)
        script_panel_layout = QVBoxLayout(script_panel)
        script_panel_layout.setContentsMargins(0, 0, 0, 0)
        script_panel_layout.setSpacing(8)
        script_panel_layout.addWidget(self.script_list, 1)
        script_panel_layout.addWidget(script_actions)

        part_details = QWidget(self)
        part_details_layout = QFormLayout(part_details)
        part_details_layout.setContentsMargins(0, 0, 0, 0)
        part_details_layout.setSpacing(10)
        part_details_layout.addRow("Name", self.part_name_editor)
        part_details_layout.addRow("Plugin", self.part_plugin_label)
        part_details_layout.addRow("Library", self.part_library_label)

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

        part_actions_layout.addWidget(part_actions_row_1)
        part_actions_layout.addWidget(part_actions_row_2)

        part_panel = QWidget(self)
        part_panel_layout = QVBoxLayout(part_panel)
        part_panel_layout.setContentsMargins(0, 0, 0, 0)
        part_panel_layout.setSpacing(8)
        part_panel_layout.addWidget(self.part_title)
        part_panel_layout.addWidget(self.part_tree, 3)
        part_panel_layout.addWidget(part_details)
        part_panel_layout.addWidget(part_actions)
        part_panel_layout.addWidget(self.log_textbox)

        body = QWidget(self)
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(14)
        body_layout.addWidget(script_panel, 1)
        body_layout.addWidget(part_panel, 2)

        layout = QVBoxLayout(self)
        layout.addWidget(body)

    def set_workspace(self, workspace: Workspace) -> None:
        self.workspace = workspace
        self.current_script_path = None
        self.new_script_button.setEnabled(True)
        self.open_button.setEnabled(True)
        self.refresh_scripts_button.setEnabled(True)
        self.delete_script_button.setEnabled(True)
        self.open_context_button.setEnabled(True)
        self.refresh_scripts()
        self.refresh_parts()
        self._reset_part_views()

    def refresh_scripts_view(self) -> None:
        previous_script = self.current_script_path
        self.refresh_scripts()

        if previous_script is not None:
            self._select_script_path(previous_script)

        current_item = self.script_list.currentItem()
        if current_item is not None:
            self._on_script_changed(current_item, None)
        else:
            self.current_script_path = None
            self.refresh_parts()
            self._reset_part_views()

    def refresh_scripts(self) -> None:
        self.script_list.clear()
        if self.workspace is None:
            return
        for script_path in self.workspace.list_scripts():
            item = QListWidgetItem(script_path.name)
            item.setData(Qt.ItemDataRole.UserRole, str(script_path))
            self.script_list.addItem(item)

    def _on_script_changed(self, current: QListWidgetItem | None, previous: QListWidgetItem | None) -> None:
        del previous
        if self.workspace is None or current is None:
            self.current_script_path = None
            self.refresh_parts()
            return

        script_path = Path(current.data(Qt.ItemDataRole.UserRole))
        self.current_script_path = script_path
        self._refresh_parts_from_script(script_path)

    def refresh_parts(self) -> None:
        self.part_tree.clear()
        if self.workspace is None:
            return

        grouped_records: dict[str, list[object]] = {}
        for record in self.workspace.list_part_records():
            grouped_records.setdefault(record.component_type, []).append(record)

        for category in sorted(grouped_records.keys()):
            category_item = QTreeWidgetItem([category, ""])
            category_item.setFirstColumnSpanned(True)
            self.part_tree.addTopLevelItem(category_item)
            for record in grouped_records.get(category, []):
                self._add_part_record_item(category_item, record)
            category_item.setExpanded(True)

        if self.part_tree.topLevelItemCount() > 0:
            first_category = self.part_tree.topLevelItem(0)
            if first_category is not None and first_category.childCount() > 0:
                first_category.setExpanded(True)
                self.part_tree.setCurrentItem(first_category.child(0))

    def _refresh_parts_from_script(self, script_path: Path) -> None:
        self.part_tree.clear()
        components = self._load_script_components(script_path)
        if not components:
            return

        records_by_component_key: dict[str, list[object]] = {}
        if self.workspace is not None:
            for record in self.workspace.list_part_records():
                if record.script_name != script_path.stem:
                    continue
                records_by_component_key.setdefault(record.component_key, []).append(record)

        components_item = QTreeWidgetItem(["COMPONENTS", ""])
        components_item.setData(0, Qt.ItemDataRole.UserRole, {"script_component": False})
        components_item.setFirstColumnSpanned(True)
        self.part_tree.addTopLevelItem(components_item)

        for key, value in components.items():
            fully_qualified_class_name = str(value)
            class_name = getattr(value, "__name__", type(value).__name__)
            item = QTreeWidgetItem([key, class_name])
            item.setData(
                0,
                Qt.ItemDataRole.UserRole,
                {
                    "script_component": True,
                    "name": str(key),
                    "class_name": str(class_name),
                    "fully_qualified_class_name": fully_qualified_class_name,
                    "option_count": len(records_by_component_key.get(str(key), [])),
                    "script_path": str(script_path),
                },
            )
            components_item.addChild(item)

            for record in records_by_component_key.get(str(key), []):
                descriptor = record.descriptor
                display_name = str(descriptor.get("Name") or record.folder.name)
                option_item = QTreeWidgetItem([display_name, str(descriptor.get("PluginType", ""))])
                option_item.setData(
                    0,
                    Qt.ItemDataRole.UserRole,
                    {
                        "existing_component": True,
                        "descriptor_path": str(record.descriptor_path),
                        "folder": str(record.folder),
                        "node_path": (),
                    },
                )
                item.addChild(option_item)

            item.setExpanded(True)

        components_item.setExpanded(True)

    def _load_script_components(self, script_path: Path) -> dict[str, Any]:
        try:
            original_cwd = Path.cwd()
            workspace_root = str(self.workspace.root) if self.workspace else None
            added_to_path = False

            try:
                if workspace_root:
                    import os

                    os.chdir(workspace_root)

                if workspace_root and workspace_root not in sys.path:
                    sys.path.insert(0, workspace_root)
                    added_to_path = True

                spec = importlib.util.spec_from_file_location("script_module", script_path)
                if spec is None or spec.loader is None:
                    return {}
                module = importlib.util.module_from_spec(spec)
                sys.modules["script_module"] = module
                spec.loader.exec_module(module)
                components = getattr(module, "COMPONENTS", {})
                return components if isinstance(components, dict) else {}
            finally:
                import os

                os.chdir(original_cwd)
                if added_to_path and workspace_root:
                    sys.path.remove(workspace_root)
                if "script_module" in sys.modules:
                    del sys.modules["script_module"]
        except Exception:
            return {}

    def _add_part_record_item(self, parent: QTreeWidgetItem, record) -> None:
        descriptor = record.descriptor
        display_name = str(descriptor.get("Name") or record.folder.name)
        item = QTreeWidgetItem([display_name, str(descriptor.get("PluginName", ""))])
        item.setData(
            0,
            Qt.ItemDataRole.UserRole,
            {
                "descriptor_path": str(record.descriptor_path),
                "folder": str(record.folder),
                "node_path": (),
            },
        )
        parent.addChild(item)
        self._populate_descriptor_children(item, descriptor, record.descriptor_path, record.folder, ())

    def _populate_descriptor_children(
        self,
        parent_item: QTreeWidgetItem,
        value: object,
        descriptor_path: Path,
        folder: Path,
        node_path: tuple[object, ...],
    ) -> None:
        if isinstance(value, dict):
            for key, child_value in value.items():
                child_item = QTreeWidgetItem([str(key), self._display_value(child_value)])
                child_item.setData(
                    0,
                    Qt.ItemDataRole.UserRole,
                    {
                        "descriptor_path": str(descriptor_path),
                        "folder": str(folder),
                        "node_path": node_path + (key,),
                    },
                )
                parent_item.addChild(child_item)
                self._populate_descriptor_children(child_item, child_value, descriptor_path, folder, node_path + (key,))
        elif isinstance(value, list):
            for index, child_value in enumerate(value):
                child_item = QTreeWidgetItem([f"[{index}]", self._display_value(child_value)])
                child_item.setData(
                    0,
                    Qt.ItemDataRole.UserRole,
                    {
                        "descriptor_path": str(descriptor_path),
                        "folder": str(folder),
                        "node_path": node_path + (index,),
                    },
                )
                parent_item.addChild(child_item)
                self._populate_descriptor_children(child_item, child_value, descriptor_path, folder, node_path + (index,))

    def _display_value(self, value: object) -> str:
        if isinstance(value, dict):
            return "{...}"
        if isinstance(value, list):
            return f"[{len(value)} items]"
        return str(value)

    def _on_part_tree_changed(self, current: QTreeWidgetItem | None, previous: QTreeWidgetItem | None) -> None:
        del previous
        if current is None:
            self._reset_part_views()
            return

        context = current.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(context, dict):
            self._reset_part_views()
            return

        if context.get("script_component") is True:
            self.current_part_folder = None
            self.current_part_descriptor_path = None
            self.current_part_node_path = ()
            self.current_part_descriptor = {}
            name = str(context.get("name", "component"))
            self.current_part_name = name
            class_name = str(context.get("class_name", ""))
            self.current_part_fully_qualified_class_name = str(context.get("fully_qualified_class_name", ""))
            self.part_title.setText(f"{name} ({class_name})")
            self.part_path_label.setText(str(context.get("script_path", "")))
            self.part_name_editor.clear()
            self.part_name_editor.setEnabled(False)
            self.part_plugin_label.setText(class_name)
            self.part_library_label.setText("-")
            option_count = int(context.get("option_count", 0))
            self.add_component_button.setText("Add Option" if option_count > 0 else "Add Component")
            self.add_component_button.setEnabled(True)
            self.remove_component_button.setEnabled(False)
            self.duplicate_component_button.setEnabled(False)
            self.part_open_params_button.setEnabled(False)
            self.part_open_context_button.setEnabled(False)
            self.part_save_name_button.setEnabled(False)
            return

        if "descriptor_path" not in context or "folder" not in context:
            self._reset_part_views()
            return

        descriptor_path = Path(context["descriptor_path"])
        folder = Path(context["folder"])
        node_path = tuple(context.get("node_path", ()))

        if self.workspace is None:
            self._reset_part_views()
            return

        try:
            descriptor = self.workspace.read_part_descriptor(folder)
        except FileNotFoundError:
            self._reset_part_views()
            return

        node = self._node_at_path(descriptor, node_path)
        if not isinstance(node, dict):
            self.current_part_folder = folder
            self.current_part_descriptor_path = descriptor_path
            self.current_part_node_path = node_path
            self.current_part_descriptor = descriptor
            self.part_title.setText(self._current_part_title(context))
            self.part_path_label.setText(str(folder))
            self.part_name_editor.setEnabled(False)
            self.part_name_editor.clear()
            self.part_plugin_label.setText(str(descriptor.get("PluginType") or ""))
            self.part_library_label.setText(str(descriptor.get("Library") or descriptor.get("Lib") or "-"))
            self.add_component_button.setEnabled(False)
            self.remove_component_button.setEnabled(False)
            self.duplicate_component_button.setEnabled(False)
            self.part_open_params_button.setEnabled(True)
            self.part_open_context_button.setEnabled(True)
            self.part_save_name_button.setEnabled(False)
            return

        self.current_part_folder = folder
        self.current_part_descriptor_path = descriptor_path
        self.current_part_node_path = node_path
        self.current_part_descriptor = descriptor
        self.part_title.setText(self._current_part_title(context))
        self.part_path_label.setText(str(folder))
        self.part_name_editor.setEnabled(True)
        self.part_name_editor.setText(str(node.get("Name", "")))
        self.part_plugin_label.setText(str(descriptor.get("PluginType") or ""))
        self.part_library_label.setText(str(descriptor.get("Library") or descriptor.get("Lib") or "-"))
        self.add_component_button.setEnabled(False)
        self.remove_component_button.setEnabled(True)
        self.duplicate_component_button.setEnabled(True)
        self.part_open_params_button.setEnabled(True)
        self.part_open_context_button.setEnabled(True)
        self.part_save_name_button.setEnabled(True)

    def _on_part_tree_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        del column
        # Force-select clicked item and refresh details even if it was already current.
        self.part_tree.setCurrentItem(item)
        self._on_part_tree_changed(item, None)

    def _current_part_title(self, context: dict[str, object]) -> str:
        descriptor_path = Path(str(context["descriptor_path"]))
        folder = Path(str(context["folder"]))
        try:
            descriptor = self.workspace.read_part_descriptor(folder) if self.workspace is not None else {}
        except FileNotFoundError:
            descriptor = {}
        name = descriptor.get("Name") or folder.name
        component_type = descriptor.get("PluginType") or descriptor_path.stem
        return f"{name} ({component_type})"

    def _node_at_path(self, payload: object, node_path: tuple[object, ...]) -> object:
        node = payload
        for step in node_path:
            if isinstance(node, dict) and isinstance(step, str):
                node = node.get(step)
            elif isinstance(node, list) and isinstance(step, int) and 0 <= step < len(node):
                node = node[step]
            else:
                return {}
        return node

    def open_selected_part_parameters(self) -> None:
        if self.workspace is None or self.current_part_folder is None:
            return
        params_path = self.workspace.part_parameters_path(self.current_part_folder)
        params_path.parent.mkdir(parents=True, exist_ok=True)
        if not params_path.exists():
            params_path.write_text("{}\n", encoding="utf-8")
        try:
            _open_in_system_editor(params_path)
        except Exception as exc:
            QMessageBox.critical(self, "Open parameters failed", str(exc))

    def open_selected_part_context(self) -> None:
        if self.current_part_folder is None:
            return
        try:
            _open_in_file_explorer(self.current_part_folder)
        except Exception as exc:
            QMessageBox.critical(self, "Open component context failed", str(exc))

    def save_selected_part_name(self) -> None:
        if self.workspace is None or self.current_part_folder is None or self.current_part_descriptor_path is None:
            return

        try:
            descriptor = self.workspace.read_part_descriptor(self.current_part_folder)
        except FileNotFoundError as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return

        node = self._node_at_path(descriptor, self.current_part_node_path)
        if not isinstance(node, dict):
            QMessageBox.information(self, "Save name", "The selected node is not editable.")
            return

        node["Name"] = self.part_name_editor.text().strip()
        self.workspace.write_part_descriptor(self.current_part_folder, descriptor)
        self.refresh_parts()
        self._reselect_part_node(self.current_part_descriptor_path, self.current_part_node_path)

    def _reselect_part_node(self, descriptor_path: Path, node_path: tuple[object, ...]) -> None:
        def matches(item: QTreeWidgetItem) -> bool:
            context = item.data(0, Qt.ItemDataRole.UserRole)
            return isinstance(context, dict) and Path(str(context.get("descriptor_path", ""))) == descriptor_path and tuple(context.get("node_path", ())) == node_path

        def walk(item: QTreeWidgetItem) -> QTreeWidgetItem | None:
            if matches(item):
                return item
            for index in range(item.childCount()):
                result = walk(item.child(index))
                if result is not None:
                    return result
            return None

        for index in range(self.part_tree.topLevelItemCount()):
            item = walk(self.part_tree.topLevelItem(index))
            if item is not None:
                self.part_tree.setCurrentItem(item)
                return

    def _reset_part_views(self, clear_tree: bool = False) -> None:
        self.current_part_folder = None
        self.current_part_descriptor_path = None
        self.current_part_node_path = ()
        self.current_part_descriptor = {}
        if clear_tree:
            self.part_tree.clear()
        self.part_title.setText("No component selected")
        self.part_name_editor.clear()
        self.part_name_editor.setEnabled(False)
        self.part_path_label.setText("")
        self.part_plugin_label.setText("")
        self.part_library_label.setText("")
        self.add_component_button.setEnabled(False)
        self.remove_component_button.setEnabled(False)
        self.duplicate_component_button.setEnabled(False)
        self.part_open_params_button.setEnabled(False)
        self.part_open_context_button.setEnabled(False)
        self.part_save_name_button.setEnabled(False)

    def open_add_component_dialog(self) -> None:
        fully_qualified_base_class_name = self.current_part_fully_qualified_class_name
        dialog = create_available_plugins_dialog(self, plugin_base_class_name=fully_qualified_base_class_name)
        if dialog is None:
            self.log_message("No compatible plugins found for Add Component.")
            QMessageBox.information(self, "Add Component", "No compatible plugins found.")
            return

        if dialog.exec() == QDialog.DialogCode.Accepted:
            plugin = dialog.selected_plugin()
            if plugin is not None:
                self._create_selected_component(plugin)

    def log_message(self, message: str) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log_textbox.appendPlainText(f"[{timestamp}] {message}")

    def _create_selected_component(self, plugin: dict[str, Any]) -> None:
        if self.workspace is None or self.current_script_path is None:
            QMessageBox.warning(self, "Add Component", "Select a script before adding a component.")
            return

        plugin_type = str(plugin.get("PluginType") or "").strip()
        if not plugin_type:
            QMessageBox.warning(self, "Add Component", "The selected entry does not define a plugin type.")
            return

        component_name = self._plugin_type_class_name(plugin_type)
        component_id = str(uuid4())
        descriptor: dict[str, Any] = {
            "Id": component_id,
            "Name": component_name,
            "PluginName": component_name,
            "ComponentKey": component_name,
            "PluginType": plugin_type,
            "Library": str(plugin.get("Library") or ""),
            "Description": "",
        }

        component_folder = self.workspace.create_part_folder(
            descriptor,
            script_name=self.current_script_path.stem,
            component_key=self.current_part_name,
        )

        self.log_message(f"Created component {component_name} at {component_folder}")
        self._refresh_current_script_parts()
        self._reselect_part_node(self.workspace.part_descriptor_path(component_folder), ())

    def remove_selected_component(self) -> None:
        if self.current_part_folder is None or self.current_script_path is None:
            return

        if QMessageBox.question(self, "Remove Component", "Remove selected component?") != QMessageBox.StandardButton.Yes:
            return

        try:
            path_shutil.rmtree(self.current_part_folder)
            self.log_message(f"Removed component at {self.current_part_folder}")
        except Exception as exc:
            QMessageBox.critical(self, "Remove Component", f"Failed to remove component: {exc}")
            return

        self._refresh_current_script_parts()
        self._reset_part_views()

    def duplicate_selected_component(self) -> None:
        if self.workspace is None or self.current_part_folder is None or self.current_script_path is None:
            return

        try:
            duplicated_folder = self._duplicate_component_folder(self.current_part_folder)
            self.log_message(f"Duplicated component to {duplicated_folder}")
        except Exception as exc:
            QMessageBox.critical(self, "Duplicate Component", f"Failed to duplicate component: {exc}")
            return

        self._refresh_current_script_parts()
        self._reselect_part_node(self.workspace.part_descriptor_path(duplicated_folder), ())

    def _duplicate_component_folder(self, source_folder: Path) -> Path:
        source_descriptor = self.workspace.read_part_descriptor(source_folder) if self.workspace is not None else {}
        source_component_id = str(source_descriptor.get("Id") or source_folder.name)
        duplicated_component_id = str(uuid4())

        target_folder = source_folder.parent / duplicated_component_id
        if target_folder.exists():
            raise FileExistsError(f"Target component already exists: {target_folder}")

        target_folder.mkdir(parents=True, exist_ok=False)

        source_descriptor_path = source_folder / "description.json"
        target_descriptor_path = target_folder / "description.json"
        if source_descriptor_path.exists():
            descriptor = json.loads(source_descriptor_path.read_text(encoding="utf-8"))
            descriptor["Id"] = duplicated_component_id
            parent_component_id = descriptor.get("ParentComponentId")
            if parent_component_id == source_component_id:
                descriptor["ParentComponentId"] = duplicated_component_id
            target_descriptor_path.write_text(json.dumps(descriptor, indent=4, sort_keys=False), encoding="utf-8")

        source_params = source_folder / "params" / "parameters.json"
        target_params = target_folder / "params" / "parameters.json"
        target_params.parent.mkdir(parents=True, exist_ok=True)
        if source_params.exists():
            target_params.write_text(source_params.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            target_params.write_text("{}\n", encoding="utf-8")

        source_callbacks = source_folder / "callbacks.py"
        target_callbacks = target_folder / "callbacks.py"
        if source_callbacks.exists():
            target_callbacks.write_text(source_callbacks.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            target_callbacks.write_text("from __future__ import annotations\n", encoding="utf-8")

        source_data_dir = source_folder / "data"
        target_data_dir = target_folder / "data"
        if source_data_dir.exists():
            path_shutil.copytree(source_data_dir, target_data_dir, dirs_exist_ok=True)
        else:
            target_data_dir.mkdir(parents=True, exist_ok=True)

        source_subcomponents_root = source_folder / "subcomponents"
        target_subcomponents_root = target_folder / "subcomponents"
        target_subcomponents_root.mkdir(parents=True, exist_ok=True)

        if source_subcomponents_root.exists():
            for slot_path in sorted(source_subcomponents_root.iterdir()):
                if not slot_path.is_dir():
                    continue
                source_slot_options = slot_path / "options"
                target_slot_options = target_subcomponents_root / slot_path.name / "options"
                target_slot_options.mkdir(parents=True, exist_ok=True)
                if source_slot_options.exists():
                    for child_component_folder in sorted(source_slot_options.iterdir()):
                        if child_component_folder.is_dir():
                            self._duplicate_component_child_tree(
                                child_component_folder,
                                target_slot_options,
                                duplicated_component_id,
                            )

        return target_folder

    def _duplicate_component_child_tree(self, source_folder: Path, target_options_root: Path, parent_component_id: str) -> None:
        duplicated_component_id = str(uuid4())
        target_folder = target_options_root / duplicated_component_id
        target_folder.mkdir(parents=True, exist_ok=False)

        source_descriptor_path = source_folder / "description.json"
        target_descriptor_path = target_folder / "description.json"
        if source_descriptor_path.exists():
            descriptor = json.loads(source_descriptor_path.read_text(encoding="utf-8"))
            descriptor["Id"] = duplicated_component_id
            descriptor["ParentComponentId"] = parent_component_id
            target_descriptor_path.write_text(json.dumps(descriptor, indent=4, sort_keys=False), encoding="utf-8")

        source_params = source_folder / "params" / "parameters.json"
        target_params = target_folder / "params" / "parameters.json"
        target_params.parent.mkdir(parents=True, exist_ok=True)
        if source_params.exists():
            target_params.write_text(source_params.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            target_params.write_text("{}\n", encoding="utf-8")

        source_callbacks = source_folder / "callbacks.py"
        target_callbacks = target_folder / "callbacks.py"
        if source_callbacks.exists():
            target_callbacks.write_text(source_callbacks.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            target_callbacks.write_text("from __future__ import annotations\n", encoding="utf-8")

        source_data_dir = source_folder / "data"
        target_data_dir = target_folder / "data"
        if source_data_dir.exists():
            path_shutil.copytree(source_data_dir, target_data_dir, dirs_exist_ok=True)
        else:
            target_data_dir.mkdir(parents=True, exist_ok=True)

        source_subcomponents_root = source_folder / "subcomponents"
        target_subcomponents_root = target_folder / "subcomponents"
        target_subcomponents_root.mkdir(parents=True, exist_ok=True)

        if source_subcomponents_root.exists():
            for slot_path in sorted(source_subcomponents_root.iterdir()):
                if not slot_path.is_dir():
                    continue
                source_slot_options = slot_path / "options"
                target_slot_options = target_subcomponents_root / slot_path.name / "options"
                target_slot_options.mkdir(parents=True, exist_ok=True)
                if source_slot_options.exists():
                    for child_component_folder in sorted(source_slot_options.iterdir()):
                        if child_component_folder.is_dir():
                            self._duplicate_component_child_tree(
                                child_component_folder,
                                target_slot_options,
                                duplicated_component_id,
                            )

    def _refresh_current_script_parts(self) -> None:
        if self.current_script_path is not None:
            self._refresh_parts_from_script(self.current_script_path)

    def _plugin_type_class_name(self, plugin_type: str) -> str:
        for plugin_type_payload in get_plugin_types().values():
            if plugin_type_payload.get("PluginType") == plugin_type:
                class_name = plugin_type_payload.get("ClassName") or plugin_type_payload.get("PluginClassName")
                if class_name:
                    return str(class_name)

        return plugin_type.split("::")[-1].strip() or "Component"

    def _selected_part_base_class_name(self) -> str | None:
        if not self.current_part_descriptor:
            return None

        plugin_type = str(self.current_part_descriptor.get("PluginType") or "").strip()
        if not plugin_type:
            return None

        for plugin_type_payload in get_plugin_types().values():
            if plugin_type_payload.get("PluginType") == plugin_type:
                return plugin_type_payload.get("FullyQualifiedBaseClassName") or plugin_type_payload.get("FullyQualifiedClassName")

        return None

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
        name, accepted = QInputDialog.getText(self, "New Script", "Script name")
        if not accepted or not name.strip():
            return
        script_name = name.strip()
        script_path = self.workspace.create_script(script_name, default_script_source(script_class_name_from_name(script_name)))
        self.refresh_scripts()
        self._select_script_path(script_path)
        self.open_selected_script(self.script_list.currentItem())

    def delete_selected_script(self) -> None:
        if self.workspace is None:
            return
        item = self.script_list.currentItem()
        if item is None:
            return
        script_path = Path(item.data(Qt.ItemDataRole.UserRole))
        if QMessageBox.question(self, "Delete script", f"Delete {script_path.name}?") != QMessageBox.StandardButton.Yes:
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

    def _select_script_path(self, script_path: Path) -> None:
        for index in range(self.script_list.count()):
            item = self.script_list.item(index)
            if Path(item.data(Qt.ItemDataRole.UserRole)) == script_path:
                self.script_list.setCurrentItem(item)
                return
