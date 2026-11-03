"""Configuration import must preserve both workspaces when copying fails."""

import copy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from rpp_orchestrator.component_storage import SubcomponentInfo
from rpp_orchestrator.workspace import create_workspace


def files_under(root):
    return {str(path.relative_to(root)): path.read_bytes()
            for path in root.rglob("*") if path.is_file()}


@pytest.fixture
def workspaces(tmp_path):
    manager = Mock()
    manager.get_library_path.return_value = None
    manager.get_plugin_info_from_lib.return_value = {
        "PluginName": "Library::Controller", "Library": "Library",
        "PluginType": "Types::Controller",
        "PluginMetadata": {"Parameters": {}, "Components": {}},
    }
    source = create_workspace(tmp_path / "source", lib_manager=manager)
    target = create_workspace(tmp_path / "target", lib_manager=manager)
    script_source = (
        "class Simulation:\n"
        "    COMPONENTS = {'controllers': 'List[Types::Controller]'}\n"
    )
    source_script = source.create_script("simulation.py", script_source)
    target_script = target.create_script("simulation.py", script_source)
    roots = [source.create_component(name, "Library::Controller")
             for name in ("first", "second")]
    existing = target.create_component("existing", "Library::Controller")
    for root in roots:
        source.assign_component_to_script(source_script, "controllers", root.id)
    return SimpleNamespace(source=source, target=target, roots=roots,
                           source_script=source_script, target_script=target_script,
                           existing=existing)


def import_configuration(workspaces):
    return workspaces.target.import_script_configuration(
        workspaces.source, workspaces.source_script, "Default",
        workspaces.target_script, "Imported")


def assert_workspace_unchanged(workspace, before_files, before_records):
    assert workspace.part_records == before_records
    assert files_under(workspace.root) == before_files


@pytest.mark.parametrize("missing", ["root", "subcomponent"])
def test_missing_component_reference_rejects_import_without_changes(workspaces, missing):
    root = workspaces.roots[0]
    if missing == "root":
        del workspaces.source.part_records[root.id]
    else:
        root.subcomponents["child"] = SubcomponentInfo(
            id="missing-child", plugin_type="Types::Controller",
            plugin_name="Library::Controller", slot_name="child", library="Library",
            folder=root.folder / "subcomponents" / "missing-child",
        )
    before_files = files_under(workspaces.target.root)
    before_records = copy.deepcopy(workspaces.target.part_records)

    with pytest.raises(ValueError, match="missing (component|subcomponent)"):
        import_configuration(workspaces)

    assert_workspace_unchanged(workspaces.target, before_files, before_records)


def test_component_name_collision_rejects_import_without_changes(workspaces):
    workspaces.target.create_component("first", "Library::Controller")
    before_files = files_under(workspaces.target.root)
    before_records = copy.deepcopy(workspaces.target.part_records)

    with pytest.raises(ValueError, match="already contains component names"):
        import_configuration(workspaces)

    assert_workspace_unchanged(workspaces.target, before_files, before_records)


@pytest.mark.parametrize("fail_on_copy", [1, 2])
def test_interrupted_copy_removes_partial_and_completed_copies(
        workspaces, monkeypatch, fail_on_copy):
    target = workspaces.target
    before_files = files_under(target.root)
    before_records = copy.deepcopy(target.part_records)
    source_files = files_under(workspaces.source.root)
    failure = OSError("copy interrupted")
    copy_folder = target.component_data_store._copy_component_folder
    attempts = 0

    def interrupted_copy(source, destination):
        nonlocal attempts
        attempts += 1
        if attempts == fail_on_copy:
            destination.mkdir(parents=True)
            (destination / "partial.txt").write_text("partial copy", encoding="utf-8")
            raise failure
        return copy_folder(source, destination)

    monkeypatch.setattr(target.component_data_store, "_copy_component_folder", interrupted_copy)

    with pytest.raises(OSError) as caught:
        import_configuration(workspaces)

    assert caught.value is failure
    assert files_under(workspaces.source.root) == source_files
    assert_workspace_unchanged(target, before_files, before_records)


@pytest.mark.parametrize("fail_on_read", [1, 2])
def test_descriptor_read_failure_after_copy_removes_copied_folder(
        workspaces, monkeypatch, fail_on_read):
    target = workspaces.target
    before_files = files_under(target.root)
    before_records = copy.deepcopy(target.part_records)
    failure = OSError("cannot read copied descriptor")
    load_description = target.component_data_store.load_description
    attempts = 0

    def failed_read(folder, **kwargs):
        nonlocal attempts
        # The duplicator also reads descriptors while rewriting their IDs.
        if kwargs:
            return load_description(folder, **kwargs)
        attempts += 1
        if attempts == fail_on_read:
            raise failure
        return load_description(folder)

    monkeypatch.setattr(target.component_data_store, "load_description", failed_read)

    with pytest.raises(OSError) as caught:
        import_configuration(workspaces)

    assert caught.value is failure
    assert_workspace_unchanged(target, before_files, before_records)


def test_descriptor_rewrite_failure_removes_partial_copy(workspaces, monkeypatch):
    target = workspaces.target
    before_files = files_under(target.root)
    before_records = copy.deepcopy(target.part_records)
    source_files = files_under(workspaces.source.root)
    failure = PermissionError("cannot rewrite copied descriptor")
    monkeypatch.setattr(target.component_data_store, "save_description", Mock(side_effect=failure))

    with pytest.raises(PermissionError) as caught:
        import_configuration(workspaces)

    assert caught.value is failure
    assert files_under(workspaces.source.root) == source_files
    assert_workspace_unchanged(target, before_files, before_records)


@pytest.mark.parametrize("partial_write", [False, True], ids=["before-write", "partial-write"])
def test_script_write_failure_restores_assignments_and_removes_copies(
        workspaces, monkeypatch, partial_write):
    target = workspaces.target
    before_files = files_under(target.root)
    before_records = copy.deepcopy(target.part_records)
    source_files = files_under(workspaces.source.root)
    description_path = workspaces.target_script.description_path
    failure = PermissionError("cannot save configuration")

    def failed_write(_description, _script_path):
        if partial_write:
            description_path.write_text('{"Configurations":', encoding="utf-8")
        raise failure

    monkeypatch.setattr(target, "_write_script_description_payload", failed_write)

    with pytest.raises(PermissionError) as caught:
        import_configuration(workspaces)

    assert caught.value is failure
    assert files_under(workspaces.source.root) == source_files
    assert_workspace_unchanged(target, before_files, before_records)


def test_repeated_reference_copies_component_once_and_rewrites_both_assignments(workspaces):
    source = workspaces.source
    script = workspaces.source_script
    root = workspaces.roots[0]
    assignment = {"Id": root.id, "PluginName": root.plugin_name}
    source.write_script_description(
        script.path, script.language,
        {"controllers": [assignment, dict(assignment)]}, script.slots)

    copied = import_configuration(workspaces)

    assert set(copied) == {root.id}
    assert len(workspaces.target.part_records) == 2
    assert workspaces.target.part_records[workspaces.existing.id] is workspaces.existing
    assert copied[root.id] != root.id
    assignments = workspaces.target_script.load_description()["Configurations"]["Imported"][
        "Components"]["controllers"]
    assert [item["Id"] for item in assignments] == [copied[root.id], copied[root.id]]
