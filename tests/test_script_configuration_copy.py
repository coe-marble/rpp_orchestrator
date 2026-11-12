from pathlib import Path

import pytest

from rpp_orchestrator.workspace import Workspace


class FakeLibraryManager:
    def __init__(self, library_path: Path) -> None:
        self.library_path = library_path

    def get_library_path(self, library_name: str):
        return str(self.library_path)


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    ws = Workspace(tmp_path, lib_manager=FakeLibraryManager(tmp_path))
    ws.ensure_layout()
    return ws


def configurations_of(ws: Workspace, script) -> dict:
    return ws.read_script_description(script.path)["Configurations"]


class TestDuplicateScriptConfiguration:
    def test_copy_keeps_every_key_of_the_source(self, workspace: Workspace) -> None:
        script = workspace.create_script("main")
        description = workspace.read_script_description(script.path)
        description["Configurations"]["Default"]["Description"] = "one toy system"
        workspace._write_script_description_payload(description, script.path)

        workspace.duplicate_script_configuration(script, "Default", "Copied")

        configurations = configurations_of(workspace, script)
        assert sorted(configurations["Copied"]) == ["Components", "Description"]
        assert configurations["Copied"]["Description"] == "one toy system"

    def test_unknown_source_configuration_is_refused(self, workspace: Workspace) -> None:
        script = workspace.create_script("main")

        with pytest.raises(ValueError, match="Configuration 'Missing' does not exist"):
            workspace.duplicate_script_configuration(script, "Missing", "Copied")
