from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

from rpp_plugin_registrator.library_manager import LibraryManager

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QMessageBox, QTreeWidgetItem

import rpp_orchestrator.gui.editor as editor_module
from rpp_orchestrator.gui.editor import WorkspaceEditor


class FakeWorkspace:
    def __init__(self, records, description):
        self.part_records = {record.id: record for record in records}
        self.description = description
        self.removed = None

    @staticmethod
    def script_configuration_components(description, configuration_name):
        return description["Configurations"][configuration_name]["Components"]

    def read_part_descriptor(self, folder):
        return next(record for record in self.part_records.values()
                    if record.folder == folder)

    def remove_component_from_script(
            self, script_handle, component_id, component_key,
            configuration_name=None):
        self.removed = (component_id, component_key, configuration_name)
        components = self.script_configuration_components(
            self.description, configuration_name
        )
        components.pop(component_key)

    def iterate_part_records(self, root_only=False):
        return iter(())


def test_configuration_selection_displays_and_removes_its_component(
        monkeypatch, tmp_path: Path):
    app = QApplication.instance() or QApplication([])

    first = SimpleNamespace(
        id="first", name="First", folder=tmp_path / "first",
        plugin_name="lib::plugin", plugin_type="type", library="lib",
    )
    second = SimpleNamespace(
        id="second", name="Second", folder=tmp_path / "second",
        plugin_name="lib::plugin", plugin_type="type", library="lib",
    )
    description = {
        "ActiveConfiguration": "Default",
        "Configurations": {
            "Default": {"Components": {"slot": [{"Id": first.id}]}},
            "Alternative": {"Components": {"slot": [{"Id": second.id}]}},
        },
    }
    workspace = FakeWorkspace([first, second], description)

    class FakeScriptHandle:
        def __init__(self, path, ws):
            self.path = path
            self.ws = ws
            self.slots = {"slot": "type"}

        def load_description(self):
            return self.ws.description

    monkeypatch.setattr(editor_module, "ScriptHandle", FakeScriptHandle)
    monkeypatch.setattr(WorkspaceEditor, "_load_plugin_types", lambda self: None)
    monkeypatch.setattr(WorkspaceEditor, "_load_plugins", lambda self: None)
    monkeypatch.setattr(LibraryManager, "__init__", lambda self, rpp_home=None, skip_layout_check=False: None)
    monkeypatch.setattr(
        WorkspaceEditor, "get_plugin_type_info", lambda self, name: None
    )
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )

    editor = WorkspaceEditor()
    assert editor.add_script_button.text() == "Add Script"
    assert [action.text() for action in editor.add_script_button.menu().actions()] == [
        "Create New…", "Link Registered…", "Load from File…"
    ]
    editor.workspace = workspace
    configuration_item = QTreeWidgetItem(["Alternative"])
    configuration_item.setData(0, Qt.ItemDataRole.UserRole, {
        "kind": "configuration",
        "script_path": str(tmp_path / "script.py"),
        "configuration_name": "Alternative",
    })

    editor._on_script_changed(configuration_item, None)

    root_item = editor.script_part_tree.topLevelItem(0)
    slot_item = root_item.child(0)
    option_item = slot_item.child(0)
    assert option_item.text(0) == "Second"

    editor.script_part_tree.setCurrentItem(option_item)
    editor.current_part_source = "script"
    editor.current_part_id = None
    editor.current_part_node_path = ("slot", second.id)
    editor.remove_selected_component()

    assert workspace.removed == (second.id, "slot", "Alternative")
    refreshed_root = editor.script_part_tree.topLevelItem(0)
    assert refreshed_root.child(0).childCount() == 0
    editor.deleteLater()
    app.processEvents()
