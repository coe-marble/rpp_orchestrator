from pathlib import Path
import shutil
import tempfile
import json
import pytest
from rpp_orchestrator.workspace import create_workspace, Workspace
from rpp_orchestrator.workspace import ComponentRecord


test_plugin_src = """
from rpp_plugin_types.rpp_testing import MotionController2D
class TestPlugin(MotionController2D):
    def name(self) -> str:
        return "test_plugin"
"""


@pytest.fixture
def temp_workspace(tmp_path):
    ws_path = tmp_path / "ws"
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    import rpp_plugin_registrator.registry_config as rp
    original_rpp_home = rp.RPP_HOME
    rp.RPP_HOME = home

    import rpp_plugin_registrator.plugin_type_registrator
    rpp_plugin_registrator.plugin_type_registrator.SCAFFOLD_LANGUAGES = ["python"]

    ws = create_workspace(ws_path, name="ws")
    handle = ws.lib_manager.get_or_create_plugin_library("testlib")
    test_plugin_file = Path(handle.path) / handle.name / "test_plugin.py"
    test_plugin_file.parent.mkdir(parents=True, exist_ok=True)
    test_plugin_file.write_text(test_plugin_src, encoding="utf-8")
    ws.lib_manager.register_plugin_from_source(test_plugin_file, "testlib")
    yield ws
    rp.RPP_HOME = original_rpp_home
    rp.reset_module()
    rpp_plugin_registrator.plugin_type_registrator.reset_module()
    shutil.rmtree(ws_path, ignore_errors=True)


def test_script_source_update_with_new_slots(temp_workspace: Workspace):
    ws = temp_workspace
    script = ws.create_script("main")
    script.add_component_slot("ctl_main", "rpp_testing::MotionController2D")
    script.add_component_slot("sensor_main", "rpp_testing::Sensor2D")

    # Read the script source and check that the slots are present
    source = script.path.read_text(encoding="utf-8")
    assert '"ctl_main":"rpp_testing::MotionController2D"' in source
    assert '"sensor_main":"rpp_testing::Sensor2D"' in source

    # Now remove a slot and check that the source is updated
    script.remove_component_slot("ctl_main")
    source = script.path.read_text(encoding="utf-8")
    assert '"ctl_main":"rpp_testing::MotionController2D"' not in source
    assert '"sensor_main":"rpp_testing::Sensor2D"' in source

def test_script_source_update_with_new_slots_no_components_field(temp_workspace: Workspace):
    ws = temp_workspace
    script = ws.create_script("main", source='''

class Main:
    def run(self):
        pass
''')

    # Now add a new component slot and check that the source is updated
    script.add_component_slot("ctl_main", "rpp_testing::MotionController2D")
    source = script.path.read_text(encoding="utf-8")
    assert 'COMPONENTS = {' in source
    assert '"ctl_main":"rpp_testing::MotionController2D"' in source

def test_create_component_with_inexisting_library_raises(temp_workspace: Workspace):
    ws = temp_workspace
    script = ws.create_script("main")
    script.add_component_slot("ctl_main", "rpp_testing::MotionController2D")

    component_name = "Controller1"
    plugin_name = "rpp::Controller"
    # Attempt to create a component with a library that doesn't exist
    with pytest.raises(ValueError) as excinfo:
        ws.create_component(
            component_name=component_name,
            plugin_name=plugin_name,
        )
    assert "Library" in str(excinfo.value)

def test_add_component_with_wrong_plugin_type_raises(temp_workspace: Workspace):
    ws = temp_workspace
    script = ws.create_script("main")
    script.add_component_slot("ctl_main", "rpp_testing::MotionController2D")

    component_name = "Controller1"
    plugin_name = "rpp_testing::Controller1"
    # Attempt to create a component with a plugin type that doesn't match the slot
    with pytest.raises(ValueError) as excinfo:
        ws.create_component(
            component_name=component_name,
            plugin_name=plugin_name,
        )
    assert "not found in library" in str(excinfo.value)

def test_add_component_and_assign_to_script(temp_workspace : Workspace):
    ws = temp_workspace
    script = ws.create_script("main")
    script.add_component_slot("ctl_main", "rpp_testing::MotionController2D")

    component_name = "Controller1"
    plugin_name = "testlib::TestPlugin"
    record = ws.create_component(
        component_name=component_name,
        plugin_name=plugin_name,
    )

    ws.assign_component_to_script(script, "ctl_main", record.id)
    record = ws.get_part_record_by_id(record.id)
    # Should appear in both workspace and script assignments
    assert record.folder.exists()
    description = ws.read_script_description(script.path)
    components = ws.active_script_components(description)
    ids = [x["Id"] for x in components["ctl_main"]]
    assert "ctl_main" in components and record.id in ids


def test_configurations_have_independent_component_assignments(
        temp_workspace: Workspace):
    ws = temp_workspace
    script = ws.create_script("configured")
    script.add_component_slot("ctl_main", "rpp_testing::MotionController2D")
    default_record = ws.create_component("Controller1", "testlib::TestPlugin")
    alternative_record = ws.create_component("Controller2", "testlib::TestPlugin")

    ws.assign_component_to_script(script, "ctl_main", default_record.id)
    ws.create_script_configuration(script, "Alternative")
    ws.assign_component_to_script(
        script,
        "ctl_main",
        alternative_record.id,
        configuration_name="Alternative",
    )

    description = ws.read_script_description(script.path)
    default_components = ws.script_configuration_components(description, "Default")
    alternative_components = ws.script_configuration_components(
        description, "Alternative"
    )
    assert [item["Id"] for item in default_components["ctl_main"]] == [
        default_record.id
    ]
    assert [item["Id"] for item in alternative_components["ctl_main"]] == [
        alternative_record.id
    ]


def test_configuration_crud_and_activation(temp_workspace: Workspace):
    ws = temp_workspace
    script = ws.create_script("configured")

    ws.create_script_configuration(script, "Alternative")
    ws.set_active_script_configuration(script, "Alternative")
    description = ws.read_script_description(script.path)
    assert description["ActiveConfiguration"] == "Alternative"

    ws.delete_script_configuration(script, "Alternative")
    description = ws.read_script_description(script.path)
    assert set(description["Configurations"]) == {"Default"}
    assert description["ActiveConfiguration"] == "Default"

    with pytest.raises(ValueError, match="at least one configuration"):
        ws.delete_script_configuration(script, "Default")


def test_rename_configuration_preserves_assignments_and_activation(
        temp_workspace: Workspace):
    ws = temp_workspace
    script = ws.create_script("configured")
    script.add_component_slot("ctl_main", "rpp_testing::MotionController2D")
    record = ws.create_component("Controller1", "testlib::TestPlugin")
    ws.assign_component_to_script(script, "ctl_main", record.id)

    ws.rename_script_configuration(script, "Default", "Primary")

    description = ws.read_script_description(script.path)
    assert set(description["Configurations"]) == {"Primary"}
    assert description["ActiveConfiguration"] == "Primary"
    components = ws.script_configuration_components(description, "Primary")
    assert [item["Id"] for item in components["ctl_main"]] == [record.id]


def test_duplicate_configuration_copies_independent_assignments(
        temp_workspace: Workspace):
    ws = temp_workspace
    script = ws.create_script("configured")
    script.add_component_slot("ctl_main", "rpp_testing::MotionController2D")
    record = ws.create_component("Controller1", "testlib::TestPlugin")
    ws.assign_component_to_script(script, "ctl_main", record.id)

    ws.duplicate_script_configuration(script, "Default", "Copy")
    description = ws.read_script_description(script.path)
    copied = ws.script_configuration_components(description, "Copy")
    assert [item["Id"] for item in copied["ctl_main"]] == [record.id]

    ws.remove_component_from_script(
        script, record.id, "ctl_main", configuration_name="Copy"
    )

    description = ws.read_script_description(script.path)
    default_components = ws.script_configuration_components(description, "Default")
    assert [item["Id"] for item in default_components["ctl_main"]] == [record.id]
    assert "ctl_main" not in ws.script_configuration_components(description, "Copy")

def test_add_component_and_assign_to_script_with_wrong_plugin_type(temp_workspace : Workspace):
    ws = temp_workspace
    script = ws.create_script("main")
    script.add_component_slot("ctl_main", "rpp_testing::MotionController3D")

    component_name = "Controller1"
    plugin_name = "testlib::TestPlugin"
    record = ws.create_component(
        component_name=component_name,
        plugin_name=plugin_name,
    )


    with pytest.raises(ValueError) as excinfo:
        ws.assign_component_to_script(script, "ctl_main", record.id)
    assert "does not match slot type" in str(excinfo.value)




def test_remove_component_from_script(temp_workspace):
    ws = temp_workspace
    script = ws.create_script("main")
    script.add_component_slot("ctl_main", "rpp_testing::MotionController2D")

    component_name = "Controller1"
    plugin_name = "testlib::TestPlugin"
    record = ws.create_component(
        component_name=component_name,
        plugin_name=plugin_name,
    )

    ws.assign_component_to_script(script, "ctl_main", record.id)

    assert record.folder.exists()
    description = ws.read_script_description(script.path)
    components = ws.active_script_components(description)
    ids = [x["Id"] for x in components["ctl_main"]]
    assert "ctl_main" in components and record.id in ids

    # Now remove the component from the script
    ws.remove_component_from_script(script, record.id, "ctl_main")
    description = ws.read_script_description(script.path)
    assert "ctl_main" not in ws.active_script_components(description)
    assert record.folder.exists()  # The component folder should still exist in the workspace
    assert ws.get_part_record_by_id(record.id) is not None  # The record should still exist in the workspace


    ws.assign_component_to_script(script, "ctl_main", record.id)
    # Now remove the component from all script keys
    ws.remove_component_from_script(script, record.id)

    description = ws.read_script_description(script.path)
    assert "ctl_main" not in ws.active_script_components(description)
    assert record.folder.exists()  # The component folder should still exist in the workspace
    assert ws.get_part_record_by_id(record.id) is not None  # The record should still exist in the workspace
