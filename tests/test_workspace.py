from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
from typing import Generator
from uuid import UUID

import pytest
from unittest import mock

MOCK_WORKSPACES_ROOT = Path(__file__).parent / "mock_workspaces"
MOCK_WORKSPACE_POPULATED = MOCK_WORKSPACES_ROOT / "mock_workspace"
MOCK_WORKSPACE_EMPTY = MOCK_WORKSPACES_ROOT / "empty_workspace"
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from rpp_orchestrator.workspace import create_workspace, default_script_source
from rpp_orchestrator.gui.available_plugins_dialog import _filter_available_plugins
from rpp_common.common_plugins import Controller, Estimator
from rpp_plugin_registrator.library_manager import LibraryManager
from rpp_plugin_registrator import registry_paths as rp


@pytest.fixture(scope="module")
def setup_plugins() -> Generator[LibraryManager, None, None]:
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        original_rpp_home = rp.RPP_HOME
        rp.RPP_HOME = home
        try:
            manager = LibraryManager(rpp_home=home / ".rpp")
            manager.get_or_create_component_library("MockLib")

            controller_source = home / "MockControllerPlugin.py"
            controller_source.write_text(
                "\n".join(
                    [
                        "from rpp_common.common_plugins import Controller",
                        "",
                        "",
                        "class MockControllerPlugin(Controller):",
                        "    tag = \"mock_ctl\"",
                        "",
                        "    def name(self) -> str:",
                        "        return \"MockControllerPlugin\"",
                        "",
                        "    def execute(self, input):",
                        "        return input",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            disturbance_source = home / "MockDisturbanceGeneratorPlugin.py"
            disturbance_source.write_text(
                "\n".join(
                    [
                        "from rpp_common.common_plugins import DisturbanceGenerator",
                        "",
                        "",
                        "class MockDisturbanceGeneratorPlugin(DisturbanceGenerator):",
                        "    tag = \"mock_dist\"",
                        "",
                        "    def name(self) -> str:",
                        "        return \"MockDisturbanceGeneratorPlugin\"",
                        "",
                        "    def on_step(self, y, dt):",
                        "        return y",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            manager.register_component_from_file(controller_source, "MockLib")
            manager.register_component_from_file(disturbance_source, "MockLib")
            yield manager
        finally:
            rp.RPP_HOME = original_rpp_home


def test_setup_registers_mock_plugins_for_available_plugins(setup_plugins: LibraryManager) -> None:
    plugins = setup_plugins.get_available_plugins()

    assert "MockLib" in plugins
    plugin_items = [item for group in plugins["MockLib"].values() for item in group]

    controller_item = next((item for item in plugin_items if item.get("ClassName") == "MockControllerPlugin"), None)
    disturbance_item = next((item for item in plugin_items if item.get("ClassName") == "MockDisturbanceGeneratorPlugin"), None)

    assert controller_item is not None
    assert disturbance_item is not None


def test_mock_script_components_are_plugin_types() -> None:
    script_path = MOCK_WORKSPACE_POPULATED / "scripts" / "example.py"
    spec = importlib.util.spec_from_file_location("mock_workspace_example", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    components = module.COMPONENTS

    assert components["ctl_main"] is Controller
    assert components["est_main"] is Estimator


def test_write_components_roundtrip(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "demo_ws", name="demo_ws")
    script_path = workspace.scripts_path / "demo_ws.py"

    payload = {
        "components": {
            "planner": {"horizon": 15, "dt": 0.1},
            "estimator": {"method": "ekf"},
        }
    }

    workspace.write_script_components(script_path, payload)
    read_back = workspace.read_script_components(script_path)

    assert read_back == payload


def test_create_workspace_layout_and_default_script(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "alpha", name="alpha")

    script_path = workspace.scripts_path / "alpha.py"

    assert workspace.scripts_path.exists()
    assert workspace.parts_path.exists()
    assert workspace.data_path.exists()
    assert workspace.builds_path.exists()
    assert workspace.logs_path.exists()
    assert script_path.exists()
    assert "COMPONENTS = {}" in script_path.read_text(encoding="utf-8")
    assert "COMPONENTS_JSON" not in script_path.read_text(encoding="utf-8")


def test_default_script_source_is_language_dependent() -> None:
    source = default_script_source("DemoScript", language="python")

    assert "from rpp_orchestrator.workspace import OrchestrationScript" in source
    assert "COMPONENTS = {}" in source
    assert "COMPONENTS_JSON" not in source
    assert "class DemoScript(OrchestrationScript):" in source


def test_mock_workspace_part_descriptor_tree() -> None:
    workspace = create_workspace(MOCK_WORKSPACE_POPULATED, name="mock_workspace", overwrite=True)

    records = workspace.list_part_records()

    assert len(records) >= 1
    root_record = next((record for record in records if record.component_key == "ctl_main"), None)
    assert root_record is not None
    assert root_record.component_type == "controller"
    assert root_record.descriptor["PluginType"] == "rpp::Controller"
    assert root_record.descriptor["Name"] == "Explicit200"
    assert root_record.descriptor["Subcomponents"] == ["Disturbance", "Subcontrollers"]
    assert workspace.part_parameters_path(root_record.folder).exists()

    disturbance_record = next((record for record in records if record.component_key == "Disturbance"), None)
    assert disturbance_record is not None
    assert disturbance_record.descriptor["PluginType"] == "rpp::DisturbanceGenerator"
    assert disturbance_record.descriptor["ParentComponentId"] == root_record.descriptor["Id"]


def test_empty_mock_workspace_has_no_parts() -> None:
    workspace = create_workspace(MOCK_WORKSPACE_EMPTY, name="empty_workspace", overwrite=True)
    records = workspace.list_part_records()
    assert records == []


def test_create_part_folder_writes_unique_descriptor(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "beta", name="beta")

    folder = workspace.create_part_folder(
        {
            "Name": "Beta Controller",
            "Description": "",
            "PluginType": "rpp::Controller",
            "PluginName": "BetaController",
            "PluginImplementation": "mat",
        },
        component_key="ctl_main",
    )

    descriptor = workspace.read_part_descriptor(folder)

    assert descriptor["Id"]
    assert descriptor["Name"] == "Beta Controller"
    assert descriptor["PluginType"] == "rpp::Controller"
    assert workspace.part_parameters_path(folder).exists()


def test_create_part_folder_uses_uuid_options_layout(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "beta", name="beta")

    folder = workspace.create_part_folder(
        {
            "Name": "Controller",
            "Description": "",
            "PluginType": "rpp::Controller",
            "PluginName": "Controller",
            "PluginImplementation": "python",
        },
        component_key="Controller",
    )

    UUID(folder.name)
    assert folder.parent.name == "options"
    assert folder.parent.parent.name == "Controller"
    assert folder.parent.parent.parent.name == "beta"
    assert workspace.part_descriptor_path(folder).exists()
    assert workspace.part_parameters_path(folder).exists()
    assert (folder / "callbacks.py").exists()


def test_filter_available_plugins_by_fully_qualified_base_class_name() -> None:
    matching_entry = {
        "Library": "TestLib",
        "PluginName": "Match",
        "ClassName": "MatchPlugin",
        "PluginType": "rpp::Controller",
        "DescriptionFile": "/tmp/MatchPlugin.py",
        "FullyQualifiedPluginClassName": "<class 'rpp_common.common_plugins.Controller.Controller'>",
    }
    non_matching_entry = {
        "Library": "TestLib",
        "PluginName": "Other",
        "ClassName": "OtherPlugin",
        "PluginType": "rpp::DisturbanceGenerator",
        "DescriptionFile": "/tmp/OtherPlugin.py",
        "FullyQualifiedPluginClassName": "<class 'rpp_common.common_plugins.DisturbanceGenerator.DisturbanceGenerator'>",
        "FullyQualifiedBaseClassName": "<class 'rpp_common.common_plugins.Controller.Controller'>",
    }

    filtered = _filter_available_plugins(
        {
            "TestLib": {
                "rpp::Controller": [matching_entry, non_matching_entry],
            },
            "OtherLib": {
                "rpp::DisturbanceGenerator": [non_matching_entry],
            },
        },
        "<class 'rpp_common.common_plugins.Controller.Controller'>",
    )

    assert filtered == {"TestLib": {"rpp::Controller": [matching_entry]}}


def test_load_available_plugins_groups_entries_by_library(setup_plugins: LibraryManager) -> None:
    from rpp_orchestrator.gui.available_plugins_dialog import _load_available_plugins

    entries_by_library = _load_available_plugins()

    assert "MockLib" in entries_by_library
    assert isinstance(entries_by_library["MockLib"], dict)
    assert any(
        entry["ClassName"] == "MockControllerPlugin"
        for group_entries in entries_by_library["MockLib"].values()
        for entry in group_entries
    )
