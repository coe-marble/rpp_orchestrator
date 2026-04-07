from __future__ import annotations

from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)


def _load_available_plugins() -> dict[str, dict[str, list[dict[str, Any]]]]:
    from rpp_plugin_registrator.library_manager import LibraryManager

    return LibraryManager().get_available_plugins()


def _entry_matches_base_class(entry: dict[str, Any], plugin_base_class_name: str) -> bool:
    return entry["FullyQualifiedPluginClassName"] == plugin_base_class_name


def _filter_available_plugins(
    entries_by_library: dict[str, dict[str, list[dict[str, Any]]]],
    plugin_base_class_name: str | None,
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    if not plugin_base_class_name:
        return entries_by_library

    filtered_entries: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for library_name, plugin_groups in entries_by_library.items():
        matching_groups: dict[str, list[dict[str, Any]]] = {}
        for plugin_type, entries in plugin_groups.items():
            matching_entries = [entry for entry in entries if _entry_matches_base_class(entry, plugin_base_class_name)]
            if matching_entries:
                matching_groups[plugin_type] = matching_entries
        if matching_groups:
            filtered_entries[library_name] = matching_groups

    return filtered_entries


class AvailablePluginsDialog(QDialog):
    def __init__(
        self,
        parent=None,
        *,
        plugin_base_class_name: str | None = None,
        entries_by_library: dict[str, dict[str, list[dict[str, Any]]]] | None = None,
    ):
        super().__init__(parent)
        self._selected_plugin: dict[str, Any] | None = None
        self._plugin_base_class_name = plugin_base_class_name
        self._entries_by_library = entries_by_library

        self.setWindowTitle("Available Plugins")
        self.resize(700, 420)

        self.summary_label = QLabel("Select a registered plugin to add to the component.", self)
        if self._plugin_base_class_name:
            self.summary_label.setText(
                f"Select a registered plugin compatible with {self._plugin_base_class_name}."
            )

        self.plugin_tree = QTreeWidget(self)
        self.plugin_tree.setColumnCount(2)
        self.plugin_tree.setHeaderLabels(["Library", "Plugin Type"])
        self.plugin_tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.plugin_tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.plugin_tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.plugin_tree.setAlternatingRowColors(True)
        self.plugin_tree.itemSelectionChanged.connect(self._update_button_state)
        self.plugin_tree.itemDoubleClicked.connect(self._accept_current_selection)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        self.add_button = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        if self.add_button is not None:
            self.add_button.setText("Add")
            self.add_button.setEnabled(False)
        self.button_box.accepted.connect(self._accept_current_selection)
        self.button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.summary_label)
        layout.addWidget(self.plugin_tree, 1)
        layout.addWidget(self.button_box)

        self._populate_plugins()

    @staticmethod
    def load_available_plugins(
        plugin_base_class_name: str | None = None,
    ) -> tuple[bool, dict[str, dict[str, list[dict[str, Any]]]]]:
        try:
            entries_by_library = _filter_available_plugins(_load_available_plugins(), plugin_base_class_name)
        except Exception:
            return False, {}

        return any(entries_by_library.values()), entries_by_library

    def _populate_plugins(self) -> None:
        try:
            entries_by_library = self._entries_by_library
            if entries_by_library is None:
                entries_by_library = _filter_available_plugins(
                    _load_available_plugins(),
                    self._plugin_base_class_name,
                )
        except Exception as exc:
            self.summary_label.setText(f"Failed to load registered plugins: {exc}")
            return

        self.plugin_tree.clear()
        for library_name in sorted(entries_by_library):
            library_item = QTreeWidgetItem([library_name, ""])
            library_item.setFirstColumnSpanned(False)
            library_item.setExpanded(True)
            self.plugin_tree.addTopLevelItem(library_item)

            for plugin_type in sorted(entries_by_library[library_name]):
                plugin_entries = entries_by_library[library_name][plugin_type]
                leaf_item = QTreeWidgetItem(["", plugin_type])
                leaf_item.setData(
                    0,
                    Qt.ItemDataRole.UserRole,
                    {
                        "Library": library_name,
                        "PluginType": plugin_type,
                        "Plugins": plugin_entries,
                    },
                )
                library_item.addChild(leaf_item)

        self.plugin_tree.expandAll()
        self._update_button_state()

    def _current_plugin_entry(self) -> dict[str, Any] | None:
        current_item = self.plugin_tree.currentItem()
        if current_item is None:
            return None

        entry = current_item.data(0, Qt.ItemDataRole.UserRole)
        return entry if isinstance(entry, dict) else None

    def _update_button_state(self) -> None:
        if self.add_button is not None:
            self.add_button.setEnabled(self._current_plugin_entry() is not None)

    def _accept_current_selection(self) -> None:
        entry = self._current_plugin_entry()
        if entry is None:
            return
        self._selected_plugin = entry
        self.accept()

    def selected_plugin(self) -> dict[str, Any] | None:
        return self._selected_plugin


def create_available_plugins_dialog(
    parent=None,
    *,
    plugin_base_class_name: str | None = None,
) -> AvailablePluginsDialog | None:
    has_entries, entries_by_library = AvailablePluginsDialog.load_available_plugins(plugin_base_class_name)
    if not has_entries:
        return None
    return AvailablePluginsDialog(
        parent,
        plugin_base_class_name=plugin_base_class_name,
        entries_by_library=entries_by_library,
    )
