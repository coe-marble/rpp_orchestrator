from pathlib import Path

import pytest

from rpp_orchestrator.workspace import ComponentRecord, Workspace

PLUGIN_TYPE = "rpp_testing::MotionController2D"


class FakeLibraryManager:
    def __init__(self, library_path: Path) -> None:
        self.library_path = library_path

    def get_library_path(self, library_name: str):
        return str(self.library_path)


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    ws = Workspace(tmp_path, lib_manager=FakeLibraryManager(tmp_path))
    ws.ensure_layout()
    for record_id in ("first", "second"):
        ws.part_records[record_id] = ComponentRecord(
            id=record_id, name=record_id, plugin_type=PLUGIN_TYPE,
            plugin_name="testlib::TestPlugin", library="testlib",
            folder=tmp_path / record_id, subcomponent_spec={},
        )
    return ws


def assigned_ids(ws: Workspace, script, slot: str) -> list[str]:
    description = ws.read_script_description(script.path)
    return [item["Id"] for item in ws.active_script_components(description)[slot]]


class TestAssignIntoFilledSlot:
    def test_single_slot_is_replaced(self, workspace: Workspace) -> None:
        script = workspace.create_script("main")
        script.add_component_slot("ctl_main", PLUGIN_TYPE)
        workspace.assign_component_to_script(script, "ctl_main", "first")

        workspace.assign_component_to_script(script, "ctl_main", "second")

        assert assigned_ids(workspace, script, "ctl_main") == ["second"]

    def test_single_slot_assigned_twice_keeps_one_entry(self, workspace: Workspace) -> None:
        script = workspace.create_script("main")
        script.add_component_slot("ctl_main", PLUGIN_TYPE)
        workspace.assign_component_to_script(script, "ctl_main", "first")

        workspace.assign_component_to_script(script, "ctl_main", "first")

        assert assigned_ids(workspace, script, "ctl_main") == ["first"]

    def test_list_slot_still_collects_components(self, workspace: Workspace) -> None:
        script = workspace.create_script("main")
        script.add_component_slot("ctl_main", f"List[{PLUGIN_TYPE}]")
        workspace.assign_component_to_script(script, "ctl_main", "first")

        workspace.assign_component_to_script(script, "ctl_main", "second")

        assert assigned_ids(workspace, script, "ctl_main") == ["first", "second"]
