from pathlib import Path
import shutil
import tempfile
import json
import pytest
from rpp_orchestrator.workspace import create_workspace, Workspace
from rpp_orchestrator.workspace import ComponentRecord


test_plugin_src = """
from rpp_plugin_types.rpp_common import MotionController2D
class TestPlugin(MotionController2D):
    def name(self) -> str:
        return "test_plugin"
"""


@pytest.fixture
def temp_workspace(tmp_path):
    ws_path = tmp_path / "ws"
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    import rpp_plugin_registrator.registry_paths as rp
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
    shutil.rmtree(ws_path, ignore_errors=True)


def test_script_source_update_with_new_slots(temp_workspace: Workspace):
    ws = temp_workspace
    script = ws.create_script("main")
    script.add_component_slot("ctl_main", "rpp_common::MotionController2D")
    script.add_component_slot("sensor_main", "rpp_common::Sensor2D")

    # Read the script source and check that the slots are present
    source = script.path.read_text(encoding="utf-8")
    assert '"ctl_main": "rpp_common::MotionController2D"' in source
    assert '"sensor_main": "rpp_common::Sensor2D"' in source

    # Now remove a slot and check that the source is updated
    script.remove_component_slot("ctl_main")
    source = script.path.read_text(encoding="utf-8")
    assert '"ctl_main": "rpp_common::MotionController2D"' not in source
    assert '"sensor_main": "rpp_common::Sensor2D"' in source

def test_add_component_with_inexisting_library_raises(temp_workspace: Workspace):
    ws = temp_workspace
    script = ws.create_script("main")
    script.add_component_slot("ctl_main", "rpp_common::MotionController2D")

    component_name = "Controller1"
    plugin_name = "rpp::Controller"
    # Attempt to create a component with a library that doesn't exist
    with pytest.raises(ValueError) as excinfo:
        ws.create_component(
            component_name=component_name,
            plugin_name=plugin_name,
            parameters={"param1": "value1"},
        )
    assert "Library" in str(excinfo.value)

def test_add_component_with_wrong_plugin_type_raises(temp_workspace: Workspace):
    ws = temp_workspace
    script = ws.create_script("main")
    script.add_component_slot("ctl_main", "rpp_common::MotionController2D")

    component_name = "Controller1"
    plugin_name = "rpp_common::Controller1"
    # Attempt to create a component with a plugin type that doesn't match the slot
    with pytest.raises(ValueError) as excinfo:
        ws.create_component(
            component_name=component_name,
            plugin_name=plugin_name,
            parameters={"param1": "value1"},
        )
    assert "not found in library" in str(excinfo.value)

def test_add_component_and_assign_to_script(temp_workspace : Workspace):
    ws = temp_workspace
    script = ws.create_script("main")
    script.add_component_slot("ctl_main", "rpp_common::MotionController2D")

    component_name = "Controller1"
    plugin_name = "testlib::TestPlugin"
    record = ws.create_component(
        component_name=component_name,
        plugin_name=plugin_name,
        parameters={"param1": "value1"},
    )

    ws.assign_component_to_script(script, "ctl_main", record.id)
    record = ws.get_part_record_by_id(record.id)
    # Should appear in both workspace and script assignments
    assert record.folder.exists()
    assignments = ws.read_script_component_assignments(script.path)
    assert "ctl_main" in assignments and record.id in assignments["ctl_main"]

def test_add_component_and_assign_to_script_with_wrong_plugin_type(temp_workspace : Workspace):
    ws = temp_workspace
    script = ws.create_script("main")
    script.add_component_slot("ctl_main", "rpp_common::MotionController3D")

    component_name = "Controller1"
    plugin_name = "testlib::TestPlugin"
    record = ws.create_component(
        component_name=component_name,
        plugin_name=plugin_name,
        parameters={"param1": "value1"},
    )


    with pytest.raises(ValueError) as excinfo:
        ws.assign_component_to_script(script, "ctl_main", record.id)
    assert "does not match slot type" in str(excinfo.value)




def test_remove_component_from_script(temp_workspace):
    ws = temp_workspace
    script = ws.create_script("main")
    script.add_component_slot("ctl_main", "rpp_common::MotionController2D")

    component_name = "Controller1"
    plugin_name = "testlib::TestPlugin"
    record = ws.create_component(
        component_name=component_name,
        plugin_name=plugin_name,
        parameters={"param1": "value1"},
    )

    ws.assign_component_to_script(script, "ctl_main", record.id)

    assert record.folder.exists()
    assignments = ws.read_script_component_assignments(script.path)
    assert "ctl_main" in assignments and record.id in assignments["ctl_main"]

    # Now remove the component from the script
    ws.remove_component_from_script(script, record.id, "ctl_main")
    assignments = ws.read_script_component_assignments(script.path)
    assert "ctl_main" not in assignments
    assert record.folder.exists()  # The component folder should still exist in the workspace

