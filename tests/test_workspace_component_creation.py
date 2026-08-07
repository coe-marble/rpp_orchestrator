from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
from typing import Generator
import types
from uuid import UUID

import pytest
from unittest import mock



RPP_TESTING_PATH = Path(__file__).parent.parent.parent.resolve() \
    / "rpp_testing" / "rpp_testing"
FIXTURE_WORKSPACES_PATH = RPP_TESTING_PATH / "data" / "mock_workspaces"

MOCK_WORKSPACE_EMPTY = FIXTURE_WORKSPACES_PATH / "empty_workspace"
MOCK_WORKSPACE_POPULATED = FIXTURE_WORKSPACES_PATH / "mock_workspace"
SAVE_MOCK_WORKSPACE_TO_PATH = False  # Set to True to save the mock workspace to disk for inspection
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from rpp_orchestrator.component_storage import LinkedComponentRecord
from rpp_orchestrator.workspace import create_workspace, open_workspace, default_script_source
from rpp_plugin_registrator.library_manager import LibraryManager
from rpp_plugin_registrator import registry_config as rp
from rpp_orchestrator.workspace import Workspace, ComponentRecord
from rpp_orchestrator.gui.assign_or_create_component_dialog import create_assign_or_create_component_dialog

from tests.utils import setup_test_plugins, create_mock_workspace


@pytest.fixture(scope="module")
def rpp_home() -> Generator[Path, None, None]:

    import rpp_plugin_registrator.plugin_type_registrator
    rpp_plugin_registrator.plugin_type_registrator.SCAFFOLD_LANGUAGES = ["python"]
    with tempfile.TemporaryDirectory() as td:
        new_home = Path(td) / ".rpp"
        original_rpp_home = rp.RPP_HOME
        rp.RPP_HOME = new_home
        try:
            yield new_home
        finally:
            rpp_plugin_registrator.plugin_type_registrator.reset_module()
            rp.RPP_HOME = original_rpp_home

@pytest.fixture
def setup_plugins(rpp_home) -> Generator[LibraryManager, None, None]:
    yield setup_test_plugins(rpp_home)

def test_setup_registers_mock_plugins_for_available_plugins(setup_plugins: LibraryManager) -> None:
    plugins = setup_plugins.get_available_plugins()

    assert "MockLib" in plugins

    controller_item = next((item for item in plugins["MockLib"]["rpp_testing::MotionController2D"] \
            if item.get("PluginName") == "MockLib::MockControllerPlugin"), None)
    disturbance_item = next((item for item in plugins["MockLib"]["rpp_testing::DisturbanceGenerator2D"] \
            if item.get("PluginName") == "MockLib::MockDisturbanceGeneratorPlugin"), None)

    assert controller_item is not None
    assert disturbance_item is not None


def test_mock_script_components_are_plugin_types(setup_plugins: LibraryManager) -> None:
    script_path = MOCK_WORKSPACE_POPULATED / "scripts" / "example.py"
    spec = importlib.util.spec_from_file_location("mock_workspace_example", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    components = module.Example.COMPONENTS

    assert components["ctl_main"] == "rpp_testing::MotionController2D"
    assert components["ctl_disturbance"] == "rpp_testing::DisturbanceGenerator2D"


def test_write_components_roundtrip(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "demo_ws", name="demo_ws")
    script_path = workspace.root / "demo_ws.py"

    payload = {
        "ScriptPath": str(script_path),
        "Language": "python",
        "Components": {
            "planner": "rpp_testing::MotionPlanner",
            "estimator": "rpp_testing::DisturbanceGenerator2D",
        }
    }

    workspace.write_script_description(script_path, "python", payload["Components"])
    read_back = workspace.read_script_description(script_path)

    assert read_back == payload


def test_create_workspace_layout_and_default_script(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "alpha", name="alpha")

    script_path = workspace.root / "alpha.py"

    assert workspace.root.exists()
    assert workspace.parts_path.exists()
    assert workspace.data_path.exists()
    assert workspace.builds_path.exists()
    assert workspace.logs_path.exists()
    assert script_path.exists()
    assert "COMPONENTS = {}" in script_path.read_text(encoding="utf-8")


def test_default_script_source_is_language_dependent() -> None:
    source = default_script_source(Path("DemoScript"))

    assert "COMPONENTS = {}" in source
    assert "class Demoscript:" in source


def test_empty_mock_workspace_has_no_parts() -> None:
    workspace = create_workspace(MOCK_WORKSPACE_EMPTY, name="empty_workspace", overwrite=True)
    records = workspace.get_part_records()
    assert records == {}


def test_create_mock_workspace_populated(setup_plugins, tmp_path: Path, rpp_home: Path) -> None:
    ws = create_mock_workspace(tmp_path, rpp_home)

    # The mock workspace should have been created with the expected structure and files
    if SAVE_MOCK_WORKSPACE_TO_PATH:
        import shutil
        shutil.rmtree(MOCK_WORKSPACE_POPULATED, ignore_errors=True)
        shutil.copytree(tmp_path / "mock_workspace", MOCK_WORKSPACE_POPULATED, dirs_exist_ok=True)

    records = ws.get_part_records()
    assert len(records) == 10
    for r in records.values():
        assert r.folder.exists()
        assert ws.part_descriptor_path(r.folder).exists()
        assert ws.part_parameters_path(r.folder).exists()
        if r.parent_component_info:
            assert r.parent_component_info.id in records
            parent_folder = records[r.parent_component_info.id].folder
            component_folder = r.folder
            assert component_folder.is_relative_to(parent_folder)


def test_create_part_folder_writes_unique_descriptor(setup_plugins, rpp_home) -> None:
    workspace = create_workspace(rpp_home / "beta", name="beta")

    record = workspace.create_component(
        "component1", "MockLib::MockControllerPlugin"
    )

    descriptor = workspace.read_part_descriptor(record.folder)

    assert descriptor.id
    assert descriptor.name == "component1"
    assert descriptor.plugin_name == "MockLib::MockControllerPlugin"
    assert descriptor.plugin_type == "rpp_testing::MotionController2D"
    assert descriptor.folder == record.folder
    assert workspace.part_parameters_path(record.folder).exists()


def test_create_part_folder_gives_unique_names_when_component_already_exists(setup_plugins, rpp_home) -> None:
    workspace = create_workspace(rpp_home / "beta_unique", name="beta_unique")

    first = workspace.create_component(
        "component1", "MockLib::MockControllerPlugin"
    )
    first_descriptor = workspace.read_part_descriptor(first.folder)

    second = workspace.create_component(
        "component1", "MockLib::MockControllerPlugin"
    )
    second_descriptor = workspace.read_part_descriptor(second.folder)
    assert first_descriptor.name == "component1"
    assert second_descriptor.name == "component1 (2)"


def test_create_subcoponent_nonexisting_slot_raises_error(setup_plugins, rpp_home) -> None:
    workspace = create_workspace(rpp_home / "beta_sub_nonexisting", name="beta_sub_nonexisting")

    parent = workspace.create_component(
        "parent_component", "MockLib::MockControllerWithSingleComponentPlugin"
    )

    slot_name = "NonExistingSlot"
    with pytest.raises(ValueError) as exc_info:
        workspace.create_subcomponent(
            parent.folder,
            slot_name,
            "disturbance1",
            "MockLib::MockControllerPlugin"
        )
    assert f"Plugin 'MockLib::MockControllerWithSingleComponentPlugin' does not have a component slot named '{slot_name}'" in str(exc_info.value)

def test_create_subcomponent_wrong_type_raises_error(setup_plugins, rpp_home) -> None:
    workspace = create_workspace(rpp_home / "beta_sub_wrong_type", name="beta_sub_wrong_type")

    parent = workspace.create_component(
        "parent_component", "MockLib::MockControllerWithSingleComponentPlugin"
    )

    slot_name = "ctl1"
    with pytest.raises(ValueError) as exc_info:
        workspace.create_subcomponent(
            parent.folder,
            slot_name,
            "disturbance1",
            "MockLib::MockDisturbanceGeneratorPlugin",  # This is the wrong type for the slot
        )
    assert f"Plugin 'MockLib::MockDisturbanceGeneratorPlugin' has an invalid type for subcomponent field '{slot_name}'" in str(exc_info.value)

def test_create_subcomponent_pass(setup_plugins, rpp_home) -> None:
    workspace = create_workspace(rpp_home / "beta_sub_unique", name="beta_sub_unique")

    parent = workspace.create_component(
        "parent_component", "MockLib::MockControllerWithSingleComponentPlugin"
    )

    slot_name = "ctl1"
    first = workspace.create_subcomponent(
        parent.folder,
        slot_name,
        "controller1",
        "MockLib::MockControllerPlugin",
    )


    assert first.folder.exists()
    assert first.parent_component_info.id == parent.id
    assert first.parent_component_info.plugin_name == parent.plugin_name
    assert first.name == "controller1"
    assert first.plugin_name == "MockLib::MockControllerPlugin"
    assert first.plugin_type == "rpp_testing::MotionController2D"
    assert first.library == "MockLib"

    parent_descriptor = workspace.read_part_descriptor(parent.folder)
    assert isinstance(parent_descriptor.subcomponents, dict) and parent_descriptor.subcomponents
    assert slot_name in parent_descriptor.subcomponents
    assert first.id == parent_descriptor.subcomponents[slot_name].id
    assert first.plugin_type == parent_descriptor.subcomponents[slot_name].plugin_type

    parent_after_first = workspace.get_component(parent.id)
    assert parent_after_first is not None
    assert parent_after_first.id == parent.id
    assert parent_after_first.subcomponents[slot_name].id == first.id
    # second subcomponent with the same slot name should
    # override the first one, since the slot is a single component slot
    second = workspace.create_subcomponent(
        parent.folder,
        slot_name,
        "controller2",
        "MockLib::MockControllerPlugin",
    )

    parent_descriptor_after_second = workspace.read_part_descriptor(parent.folder)
    assert first.id != second.id
    assert second.folder.exists()
    assert not first.folder.exists()  # The first subcomponent folder should be removed
    assert isinstance(parent_descriptor_after_second.subcomponents, dict) and parent_descriptor_after_second.subcomponents
    assert slot_name in parent_descriptor_after_second.subcomponents
    assert second.id == parent_descriptor_after_second.subcomponents[slot_name].id
    assert second.plugin_type == parent_descriptor_after_second.subcomponents[slot_name].plugin_type
    assert second.name == "controller2"

def test_create_part_folder_seeds_parameters_from_param_description(setup_plugins, tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "gamma", name="gamma")

    record = workspace.create_component(
        component_name="gamma_controller",
        plugin_name="MockLib::MockDisturbanceGeneratorPlugin",
    )

    params_path = workspace.part_parameters_path(record.folder)
    assert params_path.exists()

    read_text = params_path.read_text(encoding="utf-8")

    assert read_text == (
        "from __future__ import annotations\n"
        "\n"
        "\n"
        "class ComponentParameters:\n"
        "    param1 = 0.0\n"
        "    param2 = 1.0\n"
        "    param3 = True\n"
    )


def test_load_parameters_from_component_parameters_file(setup_plugins, tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "delta", name="delta")

    record = workspace.create_component(
        component_name="gamma_controller",
        plugin_name="MockLib::MockDisturbanceGeneratorPlugin",
    )

    # Load the parameters back from the file
    loaded_params = workspace.component_parameter_store.load(record.folder)

    assert loaded_params == {
        "param1": 0.0,
        "param2": 1.0,
        "param3": True,
    }



def test_assign_or_create_component_dialog_initialization_with_plugins_and_components(setup_plugins: LibraryManager) -> None:

    entries_by_library = setup_plugins.get_available_plugins()

    # Simulate workspace components
    workspace_components = {
        "rpp_testing::MotionController2D": [
            ComponentRecord(
                id="12345678-1234-5678-1234-567812345678",
                name="existing_component",
                plugin_name="MockLib::MockControllerPlugin",
                plugin_type="rpp_testing::MotionController2D",
                folder=Path("/tmp/existing_component"),
                library="MockLib",
                parent_component_info=None,
                subcomponent_spec={},
            )
        ],
        "rpp_testing::DisturbanceGenerator2D": [
            ComponentRecord(
                id="87654321-4321-8765-4321-876543218765",
                name="existing_disturbance",
                plugin_name="MockLib::MockDisturbanceGeneratorPlugin",
                plugin_type="rpp_testing::DisturbanceGenerator2D",
                folder=Path("/tmp/existing_disturbance"),
                library="MockLib",
                parent_component_info=None,
                subcomponent_spec={},
            )
        ],
    }

    import PyQt6.QtWidgets as QtWidgets
    QtWidgets.QDialog.__init__ = mock.MagicMock()

    import rpp_orchestrator.gui.assign_or_create_component_dialog as file
    file.QDialog.__init__ = mock.MagicMock()
    file.QLabel = mock.MagicMock()
    file.QTreeWidget = mock.MagicMock()
    file.QTreeWidgetItem = mock.MagicMock()
    file.QDialogButtonBox = mock.MagicMock()
    file.QVBoxLayout = mock.MagicMock()
    file.QMessageBox = mock.MagicMock()
    file.AssignOrCreateComponentDialog.setWindowTitle = mock.MagicMock()
    file.AssignOrCreateComponentDialog.resize = mock.MagicMock()


    def add_child_side_effect(self, child):
        if not hasattr(self, 'children'):
            self.children = []
        if hasattr(child.setData, 'call_args') and child.setData.call_args:
            data = child.setData.call_args[0][2]
            if isinstance(data, dict) \
                    and "IsPluginType" in data \
                    and not data["IsPluginType"]:
                self.children.append(child)
            else:
                self.children.append(data)
        else:
            self.children.append(child)

    def qtreewidgetitem_factory(*args, **kwargs):
        # Stvara se stvarna pod-instanca (mock objekt)
        instance = mock.MagicMock()
        # Inicijaliziramo praznu listu na toj specifičnoj instanci
        instance.children = []
        # Vežemo logiku izravno na metode TE instance
        instance.addChild.side_effect = lambda child: add_child_side_effect(instance, child)
        instance.childCount.side_effect = lambda: len(instance.children)
        return instance

    def qtreewidget_factory(*args, **kwargs):
        instance = mock.MagicMock()
        instance.children = []
        instance.topLevelItemCount.return_value = len(instance.children)
        instance.topLevelItem.side_effect = lambda index: instance.children[index] if index < len(instance.children) else None
        instance.addTopLevelItem.side_effect = lambda item: add_child_side_effect(instance, item)
        return instance
    file.QTreeWidget.side_effect = qtreewidget_factory
    file.QTreeWidgetItem.side_effect = qtreewidgetitem_factory


    dialog = create_assign_or_create_component_dialog(
        parent=None,
        workspace_components=workspace_components,
        available_plugins=entries_by_library,
        plugin_type="rpp_testing::MotionController2D",
        offer_assign=True
    )

    assert dialog is not None
    component_tree = dialog.component_tree
    plugin_tree = dialog.plugin_tree

    assert [x.id for x in component_tree.children] == ["12345678-1234-5678-1234-567812345678"]
    assert len(plugin_tree.children) == 1

    lib_children = plugin_tree.children[0]

    assert len(lib_children.children) == 1

    plugin_children = lib_children.children[0]

    assert plugin_children.addChild.call_count == 4, \
        f"Expected 4 plugin children, got {plugin_children.addChild.call_count}"


def test_load_available_plugins_groups_entries_by_library(setup_plugins: LibraryManager) -> None:

    entries_by_library = setup_plugins.get_available_plugins()

    assert "MockLib" in entries_by_library
    assert isinstance(entries_by_library["MockLib"], dict)
    assert any(
        entry["PluginName"] == "MockLib::MockControllerPlugin"
        for group_entries in entries_by_library["MockLib"].values()
        for entry in group_entries
    )

def test_mock_workspace_part_descriptor_tree(setup_plugins: LibraryManager, tmp_path: Path) -> None:

    ws = open_workspace(MOCK_WORKSPACE_POPULATED)

    records = ws.get_part_records()  # Ensure parts are loaded

    assert len(records) == 10

    parent_component = ws.get_component("parent_component")  # Ensure parent component is loaded
    child = ws.get_subcomponent(parent_component.id, "ctl1")  # Ensure child component is loaded

    assert child is not None
    assert child.parent_component_info.id == parent_component.id

    parent2_component = ws.get_component("parent2_component")  # Ensure parent2 component is loaded
    child1 = ws.get_subcomponent(parent2_component.id, "ctl1")  # Ensure child2 component is loaded
    child2 = ws.get_subcomponent(parent2_component.id, "ctl2")  # Ensure child2 component is loaded

    assert child1 is not None
    assert child2 is not None
    assert child1.parent_component_info.id == parent2_component.id
    assert child2.parent_component_info.id == parent2_component.id

    parent3_component = ws.get_component("parent3_component")  # Ensure parent3 component is loaded

    children = ws.get_subcomponent(parent3_component.id, "ctl1")  # Ensure child components are loaded

    assert isinstance(children, list)
    assert len(children) == 2

    assert all(child.parent_component_info.id == parent3_component.id for child in children)
    assert {child.name for child in children} == {"parent3_child1", "parent3_child2"}

def test_remove_component_removes_subcomponents(setup_plugins: LibraryManager, tmp_path: Path) -> None:

    ws : Workspace = create_mock_workspace(tmp_path, setup_plugins.rpp_home)

    parent_component = ws.get_component("parent_component")
    child = ws.get_subcomponent(parent_component.id, "ctl1")

    assert parent_component is not None
    assert child is not None

    # Remove the parent component
    ws.remove_component(parent_component.id)

    assert not parent_component.folder.exists()
    assert not child.folder.exists()

def test_remove_subcomponent_removes_only_subcomponent(setup_plugins: LibraryManager, tmp_path: Path) -> None:

    ws : Workspace = create_mock_workspace(tmp_path, setup_plugins.rpp_home)

    parent_component = ws.get_component("parent2_component")
    child1 = ws.get_subcomponent(parent_component.id, "ctl1")
    child2 = ws.get_subcomponent(parent_component.id, "ctl2")

    assert parent_component is not None
    assert child1 is not None
    assert child2 is not None

    # Remove the first subcomponent
    ws.remove_subcomponent(parent_component.id, "ctl1", child1.id, handle_parent_update=True)

    assert not child1.folder.exists()
    assert child2.folder.exists()
    assert parent_component.folder.exists()

    parent_after_removal = ws.get_component(parent_component.id)
    assert parent_after_removal is not None
    assert "ctl1" not in parent_after_removal.subcomponents
    assert "ctl2" in parent_after_removal.subcomponents

def test_assign_subcomponent_to_parent_then_remove(setup_plugins: LibraryManager, tmp_path: Path) -> None:

    ws : Workspace = create_workspace(
        tmp_path / "assign_subcomponent_workspace",
        name="assign_subcomponent_workspace")

    parent_component = ws.create_component(
        component_name="parent_component",
        plugin_name="MockLib::MockControllerWithSingleComponentPlugin"
    )

    child_component = ws.create_component(
        component_name="child_component",
        plugin_name="MockLib::MockControllerPlugin"
    )

    parent_component, new_child = ws.assign_subcomponent_to_parent(
        parent_component_id_or_name=parent_component.id,
        slot_name="ctl1",
        subcomponent_id=child_component.id
    )

    assert new_child is not None
    assert isinstance(new_child, LinkedComponentRecord)
    assert new_child.parent_component_info.id == parent_component.id
    assert new_child.id != child_component.id  # Ensure the linked component has a different ID

    components = ws.get_part_records()
    assert new_child.id in components
    assert child_component.id in components

    ws.remove_component(new_child.id)

    components = ws.get_part_records()
    assert new_child.id not in components  # The linked component should be removed
    assert child_component.id in components  # The original child component should still exist
    assert not new_child.folder.exists()
    assert child_component.folder.exists()  # The original child component should still exist
    assert parent_component.folder.exists()  # The parent component should still exist


def test_assign_subcomponent_to_parent_then_remove_linked_component_raises(
        setup_plugins: LibraryManager, tmp_path: Path) -> None:

    ws : Workspace = create_workspace(
        tmp_path / "assign_subcomponent_workspace",
        name="assign_subcomponent_workspace")

    parent_component = ws.create_component(
        component_name="parent_component",
        plugin_name="MockLib::MockControllerWithSingleComponentPlugin"
    )

    child_component = ws.create_component(
        component_name="child_component",
        plugin_name="MockLib::MockControllerPlugin"
    )

    parent_component, new_child = ws.assign_subcomponent_to_parent(
        parent_component_id_or_name=parent_component.id,
        slot_name="ctl1",
        subcomponent_id=child_component.id
    )

    with pytest.raises(ValueError) as exc_info:
        ws.remove_component(child_component.id)

    assert "Cannot remove component" in str(exc_info.value)

def test_duplicate_component_simple(setup_plugins: LibraryManager, tmp_path: Path) -> None:

    ws : Workspace = create_mock_workspace(tmp_path, setup_plugins.rpp_home)

    parent_component = ws.get_component("parent_component")
    child = ws.get_subcomponent(parent_component.id, "ctl1")

    assert parent_component is not None
    assert child is not None

    assert parent_component.subcomponents["ctl1"].id == child.id

    # Duplicate the parent component
    duplicated_parent = ws.duplicate_component(parent_component.id, new_name="duplicated_parent")

    assert duplicated_parent is not None
    assert duplicated_parent.name == "duplicated_parent"
    assert duplicated_parent.folder.exists()
    assert duplicated_parent.id != parent_component.id  # Ensure the duplicated parent has a different ID
    assert duplicated_parent.plugin_name == parent_component.plugin_name  # Ensure the plugin name is the same
    assert duplicated_parent.subcomponents.keys() == parent_component.subcomponents.keys()  # Ensure the subcomponent slots are the same



    # Check that the duplicated parent has a subcomponent in the same slot
    duplicated_child = ws.get_subcomponent(duplicated_parent.id, "ctl1")
    assert duplicated_child is not None
    assert duplicated_child.folder.exists()
    assert duplicated_child.id != child.id  # Ensure the duplicated child has a different ID
    assert child.plugin_name == duplicated_child.plugin_name  # Ensure the plugin name is the same
    assert child.folder.name != duplicated_child.folder.name  # Ensure the folder names are different
    assert duplicated_child.parent_component_info.id == duplicated_parent.id  # Ensure the duplicated child's parent ID matches the duplicated parent

    assert duplicated_parent.subcomponents["ctl1"].id == duplicated_child.id  # Ensure the duplicated parent's subcomponent slot points to the duplicated child

def test_duplicate_component_with_recursive_subcomponents(setup_plugins: LibraryManager, tmp_path: Path) -> None:

    ws : Workspace = create_mock_workspace(tmp_path, setup_plugins.rpp_home)

    parent_component = ws.get_component("parent3_component")
    children = ws.get_subcomponent(parent_component.id, "ctl1")

    assert isinstance(children, list)
    assert len(children) == 2
    child1 = next((c for c in children if c.name == "parent3_child1"), None)
    child2 = next((c for c in children if c.name == "parent3_child2"), None)

    child_of_child2 = ws.get_subcomponent(child2.id, "ctl1") if child2 else None

    assert parent_component is not None
    assert child1 is not None
    assert child2 is not None
    assert child_of_child2 is not None


    assert child1.parent_component_info.id == parent_component.id
    assert child2.parent_component_info.id == parent_component.id
    assert child_of_child2.parent_component_info.id == child2.id

    assert parent_component.folder.exists()
    assert child1.folder.exists()
    assert child2.folder.exists()
    assert child_of_child2.folder.exists()

    for ch in parent_component.subcomponents["ctl1"]:
        assert ch.id in [child1.id, child2.id]

    assert child2.subcomponents["ctl1"].id == child_of_child2.id

    # Duplicate the parent component
    duplicated_parent = ws.duplicate_component(parent_component.id, new_name="duplicated_parent2")

    assert duplicated_parent is not None
    assert duplicated_parent.name == "duplicated_parent2"
    assert duplicated_parent.folder.exists()



    # Check that the duplicated parent has subcomponents in the same slots
    duplicated_children = ws.get_subcomponent(duplicated_parent.id, "ctl1")

    assert isinstance(duplicated_children, list)
    assert len(duplicated_children) == 2

    duplicated_child1 = next((c for c in duplicated_children if c.name == "parent3_child1"), None)
    duplicated_child2 = next((c for c in duplicated_children if c.name == "parent3_child2"), None)

    duplicated_child_of_child2 = ws.get_subcomponent(duplicated_child2.id, "ctl1") if duplicated_child2 else None
    assert duplicated_child1 is not None
    assert duplicated_child2 is not None
    assert duplicated_child_of_child2 is not None

    assert duplicated_child1.folder.exists()
    assert duplicated_child2.folder.exists()
    assert duplicated_child_of_child2.folder.exists()


    assert duplicated_child1.parent_component_info.id == duplicated_parent.id
    assert duplicated_child2.parent_component_info.id == duplicated_parent.id
    assert duplicated_child_of_child2.parent_component_info.id == duplicated_child2.id

    assert duplicated_child1.id != child1.id
    assert duplicated_child2.id != child2.id
    assert duplicated_child_of_child2.id != child_of_child2.id

    assert duplicated_child1.plugin_name == child1.plugin_name
    assert duplicated_child2.plugin_name == child2.plugin_name
    assert duplicated_child_of_child2.plugin_name == child_of_child2.plugin_name

    for ch in duplicated_parent.subcomponents["ctl1"]:
        assert ch.id in [duplicated_child1.id, duplicated_child2.id]

    assert duplicated_child2.subcomponents["ctl1"].id == duplicated_child_of_child2.id


def test_duplicate_component_with_linked_subcomponent(setup_plugins: LibraryManager, tmp_path: Path) -> None:

    ws : Workspace = create_workspace(
        tmp_path / "duplicate_linked_subcomponent_workspace",
        name="duplicate_linked_subcomponent_workspace")

    parent_component = ws.create_component(
        component_name="parent_component",
        plugin_name="MockLib::MockControllerWithSingleComponentPlugin"
    )

    child_component = ws.create_component(
        component_name="child_component",
        plugin_name="MockLib::MockControllerPlugin"
    )

    parent_component, linked_child = ws.assign_subcomponent_to_parent(
        parent_component_id_or_name=parent_component.id,
        slot_name="ctl1",
        subcomponent_id=child_component.id
    )

    components = ws.get_part_records()

    assert len(components) == 3

    # Duplication of linked component should raise an error
    with pytest.raises(ValueError) as excinfo:
        ws.duplicate_component(linked_child.id, new_name="duplicated_linked_child")

    assert "Cannot duplicate a linked component" in str(excinfo.value)

    components = ws.get_part_records()

    assert len(components) == 3  # Ensure no new components were created

    duplicated = ws.duplicate_component(parent_component.id, new_name="duplicated_parent_with_linked_child")

    components = ws.get_part_records()

    assert len(components) == 5  # Parent and linked child should be duplicated, so total count increases by 2

    assert duplicated is not None
    assert duplicated.name == "duplicated_parent_with_linked_child"
    assert duplicated.folder.exists()

    assert duplicated.folder != parent_component.folder

    duplicated_linked_child = ws.get_subcomponent(duplicated.id, "ctl1")

    assert duplicated_linked_child is not None
    assert duplicated_linked_child.folder.exists()
    assert duplicated_linked_child.id != linked_child.id
    assert duplicated_linked_child.linked_component_id == child_component.id
