from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QSignalBlocker, Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)




def _entry_matches_base_class(entry: dict[str, Any], plugin_base_class_name: str) -> bool:
    return entry["FullyQualifiedPluginClassName"] == plugin_base_class_name


def _filter_available_plugins(
    entries_by_library: dict[str, dict[str, list[dict[str, Any]]]],
    plugin_type: str | None,
) -> dict[str, list[dict[str, Any]]]:
    if not plugin_type:
        # When no filter, flatten the nested structure
        return entries_by_library

    filtered_entries: dict[str, list[dict[str, Any]]] = {}
    for library_name, plugin_groups in entries_by_library.items():
        if plugin_type in plugin_groups:
            filtered_entries[library_name] = plugin_groups[plugin_type]

    return filtered_entries


class AssignOrCreateComponentDialog(QDialog):
    def __init__(
        self,
        workspace_components: list[dict[str, Any]],
        available_plugins: dict[str, dict[str, list[dict[str, Any]]]],
        parent=None,
        *,
        plugin_type: str | None = None,
    ):
        super().__init__(parent)

        if available_plugins is None:
            raise ValueError("available_plugins must be provided.")

        self.workspace_components = workspace_components

        self._selected_plugin: dict[str, Any] | None = None
        self._plugin_type = plugin_type
        self._entries_by_library = \
            _filter_available_plugins(available_plugins, plugin_type)

        if not self._entries_by_library:
            self._selected_plugin = None
            self.has_plugins = False
            self.reject()
            return

        self.has_plugins = True
        self.setWindowTitle("Available Plugins")
        self.resize(700, 420)

        self.summary_label_component = QLabel("Select an existing component for the script.", self)
        self.summary_label_plugin = QLabel("OR Select a registered plugin to create a new component.", self)
        self.plugin_tree = QTreeWidget(self)
        self.plugin_tree.setColumnCount(2)
        self.plugin_tree.setHeaderLabels(["Library", "Plugin Type"])
        self.plugin_tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.plugin_tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.plugin_tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.plugin_tree.setAlternatingRowColors(True)
        self.plugin_tree.itemSelectionChanged.connect(lambda: self._update_button_state("plugin"))
        self.plugin_tree.itemDoubleClicked.connect(lambda: self._accept_current_selection("plugin"))

        self.component_tree = QTreeWidget(self)
        self.component_tree.setColumnCount(2)
        self.component_tree.setHeaderLabels(["Component Name", "Plugin Name"])
        self.component_tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.component_tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.component_tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.component_tree.setAlternatingRowColors(True)
        self.component_tree.itemSelectionChanged.connect(lambda: self._update_button_state("component"))
        self.component_tree.itemDoubleClicked.connect(lambda: self._accept_current_selection("component"))

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        self.add_button = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        if self.add_button is not None:
            self.add_button.setText("Add")
            self.add_button.setEnabled(False)
        self.button_box.accepted.connect(lambda: self._accept_current_selection("button"))
        self.button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.summary_label_component)
        layout.addWidget(self.component_tree, 1)
        layout.addWidget(self.summary_label_plugin)
        layout.addWidget(self.plugin_tree, 1)
        layout.addWidget(self.button_box)

        self._populate_components()
        self._populate_plugins()


    def _populate_components(self) -> None:
        self.component_tree.clear()

        plugin_components = self.workspace_components.get(self._plugin_type, [])

        for component in plugin_components:
            record = component
            component_name = record.name
            plugin_name = record.plugin_name
            leaf_item = QTreeWidgetItem([component_name, plugin_name])
            leaf_item.setData(
                0,
                Qt.ItemDataRole.UserRole,
                component,
            )
            self.component_tree.addTopLevelItem(leaf_item)
        self.component_tree.expandAll()
        self.component_tree.resizeColumnToContents(0)
        self._update_button_state()

    def _populate_plugins(self) -> None:
        entries_by_library = self._entries_by_library

        self.plugin_tree.clear()
        for library_name in sorted(entries_by_library.keys()):

            assert isinstance(entries_by_library[library_name], list)

            library_item = QTreeWidgetItem([library_name, ""])
            library_item.setFirstColumnSpanned(False)
            library_item.setExpanded(True)

            # assert entries have more than one plugin type
            for plugin in entries_by_library[library_name]:
                plugin_name = plugin["PluginName"]
                leaf_item = QTreeWidgetItem(["", plugin_name])
                leaf_item.setData(
                    0,
                    Qt.ItemDataRole.UserRole,
                    plugin,
                )
                library_item.addChild(leaf_item)

            if library_item.childCount() > 0:
                self.plugin_tree.addTopLevelItem(library_item)
        self.plugin_tree.expandAll()
        self.plugin_tree.resizeColumnToContents(0)
        self._update_button_state()

    def _current_entry(self) -> dict[str, Any] | None:
        current_item = self.plugin_tree.currentItem()
        if current_item is not None:
            return "plugin", current_item.data(0, Qt.ItemDataRole.UserRole)
        current_item = self.component_tree.currentItem()
        if current_item is not None:
            return "component", current_item.data(0, Qt.ItemDataRole.UserRole)
        return None

    def _update_button_state(self, source: str | None = None) -> None:

        if source:
            if source == "component":
                with QSignalBlocker(self.plugin_tree):
                    self.plugin_tree.clearSelection()
            elif source == "plugin":
                with QSignalBlocker(self.component_tree):
                    self.component_tree.clearSelection()

        if self.add_button is not None:
            self.add_button.setEnabled(self._current_entry() is not None)

    def _accept_current_selection(self, source: str) -> None:
        entry_src, entry = self._current_entry()
        if entry_src != source:
            raise ValueError(f"Current entry source {entry_src} does not match expected source {source}")
        if source == "component":
            self._selected_plugin = None
            self._selected_component = entry
        elif source == "plugin":
            self._selected_plugin = entry
            self._selected_component = None
        else:
            raise ValueError(f"Unknown source: {source}")
        self.accept()

    def get_selected_item(self) -> dict[str, Any] | None:
        if self._selected_plugin is not None:
            return "plugin", self._selected_plugin
        elif self._selected_component is not None:
            return "component", self._selected_component
        return None

def create_assign_or_create_component_dialog(
    parent=None,
    workspace_components=None,
    available_plugins=None,
    *,
    plugin_type: str | None = None,
) -> AssignOrCreateComponentDialog | None:
    return AssignOrCreateComponentDialog(
        workspace_components=workspace_components,
        available_plugins=available_plugins,
        parent=parent,
        plugin_type=plugin_type,
    )
