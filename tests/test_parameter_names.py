import json
from pathlib import Path

import pytest

from rpp_orchestrator.component_storage import ComponentParameterStore


class FakeLibraryManager:
    def get_plugin_info_from_lib(self, plugin_name: str):
        assert plugin_name == "demo::Toy"
        return {"PluginMetadata": {"Parameters": {
            "count": {"name": "count", "type": "int", "default_value": 3},
            "mode": {"name": "mode", "type": "string", "default_value": "fast"},
        }}}


@pytest.fixture
def component_folder(tmp_path: Path) -> Path:
    folder = tmp_path / "component"
    folder.mkdir()
    (folder / "description.json").write_text(
        json.dumps({"PluginName": "demo::Toy"}), encoding="utf-8")
    return folder


@pytest.fixture
def store() -> ComponentParameterStore:
    return ComponentParameterStore(lib_manager=FakeLibraryManager())


class TestSaveParameterNames:
    def test_declared_name_is_saved(self, store, component_folder: Path) -> None:
        store.save(component_folder, {"count": 5})

        assert store.load(component_folder) == {"count": 5}

    def test_undeclared_name_is_refused_with_the_declared_names(
            self, store, component_folder: Path) -> None:
        with pytest.raises(ValueError, match="'cuont' is not declared.*count, mode"):
            store.save(component_folder, {"cuont": 5})

        assert not store.parameters_path(component_folder).exists()

    def test_name_already_stored_stays_editable(self, store, component_folder: Path) -> None:
        store.ensure_parameters_file(component_folder, {"removed": 1})
        parameters = store.load(component_folder)
        parameters["count"] = 5

        store.save(component_folder, parameters)

        assert store.load(component_folder) == {"removed": 1, "count": 5}

    def test_unregistered_plugin_is_not_checked(self, component_folder: Path) -> None:
        class UnknownPluginManager:
            def get_plugin_info_from_lib(self, plugin_name: str):
                raise ValueError(f"Plugin '{plugin_name}' not found in library 'demo'")

        store = ComponentParameterStore(lib_manager=UnknownPluginManager())
        store.save(component_folder, {"anything": 1})

        assert store.load(component_folder) == {"anything": 1}
