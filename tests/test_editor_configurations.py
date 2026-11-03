from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace

from fake_qt_helpers import install_fake_qt


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
    qt = install_fake_qt(monkeypatch)
    editor_module = importlib.import_module("rpp_orchestrator.gui.editor")
    WorkspaceEditor = editor_module.WorkspaceEditor

    def fake_editor_init(self):
        self.workspace = None
        self.current_script_handle = None
        self.current_configuration_name = None
        self.current_part_source = ""
        self.current_part_id = None
        self.current_part_node_path = ()
        self.script_tree = qt.TreeWidget()
        self.script_part_tree = qt.TreeWidget()
        self.workspace_components_tree = qt.TreeWidget()
        self.log_textbox = qt.Log()
        self.script_management_actions = qt.Control()
        self.configuration_actions = qt.Control()
        self.debug_script_button = qt.Control()
        self.new_configuration_button = qt.Control()
        self.duplicate_configuration_button = qt.Control()
        self.rename_configuration_button = qt.Control()
        self.delete_configuration_button = qt.Control()

    monkeypatch.setattr(WorkspaceEditor, "__init__", fake_editor_init)

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
    monkeypatch.setattr(
        WorkspaceEditor, "get_plugin_type_info", lambda self, name: None
    )
    monkeypatch.setattr(
        editor_module.QMessageBox, "question",
        lambda *args, **kwargs: qt.MessageBox.StandardButton.Yes,
    )

    editor = WorkspaceEditor()
    editor.workspace = workspace
    configuration_item = qt.TreeWidgetItem(["Alternative"])
    configuration_item.setData(0, qt.Qt.ItemDataRole.UserRole, {
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
    monkeypatch.setattr(editor, "_reset_part_views", lambda: None)
    monkeypatch.setattr(editor, "_refresh_workspace_components_tree", lambda: None)
    monkeypatch.setattr(editor, "_reselect_workspace_part_node", lambda path: None)
    editor.remove_selected_component()

    assert workspace.removed == (second.id, "slot", "Alternative")
    refreshed_root = editor.script_part_tree.topLevelItem(0)
    assert refreshed_root.child(0).childCount() == 0
