import tempfile
from pathlib import Path
from typing import Generator
import pytest

import rpp_plugin_registrator.registry_config as rp
from rpp_plugin_registrator.library_manager import LibraryManager
from rpp_orchestrator.component_storage import ComponentDataStore

from tests.utils import setup_test_plugins


RPP_TESTING_PATH = Path(__file__).parent.parent.parent.resolve() \
    / "rpp_testing" / "rpp_testing"
FIXTURE_WORKSPACES_PATH = RPP_TESTING_PATH / "data" / "mock_workspaces"

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
            rp.RPP_HOME = original_rpp_home
            rpp_plugin_registrator.plugin_type_registrator.reset_module()

@pytest.fixture
def mock_workspace_root():
    return FIXTURE_WORKSPACES_PATH / "mock_workspace"

@pytest.fixture
def new_test_workspace(tmp_path: Path) -> Generator[Path, None, None]:
    workspace_root = tmp_path / "mock_workspace"
    workspace_root.mkdir(parents=True, exist_ok=True)
    yield workspace_root

@pytest.fixture
def setup_plugins(rpp_home) -> Generator[LibraryManager, None, None]:
    yield setup_test_plugins(rpp_home)


def test_create_component_folder_then_remove_component(new_test_workspace: Path, rpp_home: Path, setup_plugins: LibraryManager) -> None:
    lm = setup_plugins
    # Create a new ComponentDataStore
    store = ComponentDataStore(new_test_workspace / "parts", lib_manager=lm)
    record = store.create_component_folder("test_component", "MockLib::MockControllerPlugin")

    assert record is not None
    assert record.folder.exists()
    assert record.folder.is_dir()
    assert record.plugin_name == "MockLib::MockControllerPlugin"
    assert record.name == "test_component"

    store.remove_component_folder(record.folder)

    assert not record.folder.exists()


def test_create_component_folder_and_rename(new_test_workspace: Path, rpp_home: Path, setup_plugins: LibraryManager) -> None:
    lm = setup_plugins
    # Create a new ComponentDataStore
    store = ComponentDataStore(new_test_workspace / "parts", lib_manager=lm)
    record = store.create_component_folder("test_component", "MockLib::MockControllerPlugin")

    assert record is not None
    assert record.folder.exists()
    assert record.folder.is_dir()
    assert record.plugin_name == "MockLib::MockControllerPlugin"
    assert record.name == "test_component"

    new_name = "renamed_component"
    new_record = store.rename_component_folder(record.folder, new_name)

    new_record = store.load_description(new_record.folder)

    assert new_record is not None
    assert new_record.folder.exists()
    assert new_record.folder.is_dir()
    assert new_record.plugin_name == "MockLib::MockControllerPlugin"
    assert new_record.name == new_name

def test_create_component_folder_then_change_plugin(new_test_workspace: Path, rpp_home: Path, setup_plugins: LibraryManager) -> None:
    lm = setup_plugins
    # Create a new ComponentDataStore
    store = ComponentDataStore(new_test_workspace / "parts", lib_manager=lm)
    record = store.create_component_folder("test_component", "MockLib::MockControllerPlugin")

    assert record is not None
    assert record.folder.exists()
    assert record.folder.is_dir()
    assert record.plugin_name == "MockLib::MockControllerPlugin"
    assert record.name == "test_component"

    old_folder = record.folder
    new_plugin_name = "MockLib::MockDisturbanceGeneratorPlugin"
    new_record = store.change_component_plugin_name(record.folder, new_plugin_name)

    new_record = store.load_description(new_record.folder)

    old_exists = old_folder.exists()

    assert not old_folder.exists()  # The folder should not exist anymore after changing the plugin
    assert new_record is not None
    assert new_record.folder.exists()
    assert new_record.folder.is_dir()
    assert new_record.plugin_name == new_plugin_name
    assert new_record.name == "test_component"

def test_create_component_folder_then_save_load_roundtrip(new_test_workspace: Path, rpp_home: Path, setup_plugins: LibraryManager) -> None:
    lm = setup_plugins
    # Create a new ComponentDataStore
    store = ComponentDataStore(new_test_workspace / "parts", lib_manager=lm)
    record = store.create_component_folder("test_component", "MockLib::MockControllerPlugin")

    # Load the store again
    loaded_store = ComponentDataStore(new_test_workspace / "parts", lib_manager=lm)
    loaded_record = loaded_store.load_description(record.folder)

    assert loaded_record is not None
    assert loaded_record.folder.exists()
    assert loaded_record.folder.is_dir()
    assert loaded_record.plugin_name == "MockLib::MockControllerPlugin"
    assert loaded_record.name == "test_component"

    loaded_store.save_description(loaded_record.folder,loaded_record)
    record = loaded_store.load_description(loaded_record.folder)

    assert record is not None
    assert record.folder.exists()
    assert record.folder.is_dir()
    assert record.plugin_name == "MockLib::MockControllerPlugin"
    assert record.name == "test_component"


def test_create_subcomponent_folder_then_remove_subcomponent(new_test_workspace: Path, rpp_home: Path, setup_plugins: LibraryManager) -> None:
    lm = setup_plugins
    # Create a new ComponentDataStore
    store = ComponentDataStore(new_test_workspace / "parts", lib_manager=lm)
    parent_record = store.create_component_folder("parent_component", "MockLib::MockControllerPlugin")
    parent_record_new, subcomponent_record = \
        store.create_subcomponent_folder(parent_record.folder,
                "subcomponent",
                "AwesomeSubcomponent",
                "MockLib::MockDisturbanceGeneratorPlugin")
    store.save_description(parent_record_new.folder, parent_record_new)
    store.save_description(subcomponent_record.folder, subcomponent_record)

    assert subcomponent_record is not None
    assert subcomponent_record.folder.exists()
    assert subcomponent_record.folder.is_dir()
    assert subcomponent_record.plugin_name == "MockLib::MockDisturbanceGeneratorPlugin"
    assert subcomponent_record.name == "AwesomeSubcomponent"
    assert parent_record_new.subcomponents.get("subcomponent") is not None

    assert parent_record_new is not None
    assert parent_record_new.folder.exists()
    assert parent_record_new.folder.is_dir()
    assert parent_record_new.plugin_name == "MockLib::MockControllerPlugin"
    assert parent_record_new.name == "parent_component"

    store.remove_subcomponent_folder(subcomponent_record.folder)

    after_removal_parent_record = store.load_description(parent_record_new.folder)

    assert not subcomponent_record.folder.exists()
    assert parent_record_new.folder.exists()
    assert after_removal_parent_record.folder == parent_record_new.folder
    assert after_removal_parent_record.plugin_name == "MockLib::MockControllerPlugin"

def test_create_subcomponent_folder_then_rename_subcomponent(new_test_workspace: Path, rpp_home: Path, setup_plugins: LibraryManager) -> None:
    lm = setup_plugins
    # Create a new ComponentDataStore
    store = ComponentDataStore(new_test_workspace / "parts", lib_manager=lm)
    parent_record = store.create_component_folder("parent_component", "MockLib::MockControllerPlugin")
    parent_record_new, subcomponent_record = \
        store.create_subcomponent_folder(parent_record.folder,
                "subcomponent",
                "AwesomeSubcomponent",
                "MockLib::MockDisturbanceGeneratorPlugin")

    store.save_description(parent_record_new.folder, parent_record_new)
    store.save_description(subcomponent_record.folder, subcomponent_record)

    assert subcomponent_record is not None
    assert subcomponent_record.folder.exists()
    assert subcomponent_record.folder.is_dir()

    assert subcomponent_record.plugin_name == "MockLib::MockDisturbanceGeneratorPlugin"
    assert subcomponent_record.name == "AwesomeSubcomponent"

    new_name = "RenamedSubcomponent"
    renamed_subcomponent_record = \
        store.rename_component_folder(subcomponent_record.folder, new_name)

    assert renamed_subcomponent_record is not None
    assert renamed_subcomponent_record.folder.exists()
    assert renamed_subcomponent_record.folder.is_dir()
    assert renamed_subcomponent_record.plugin_name == "MockLib::MockDisturbanceGeneratorPlugin"
    assert renamed_subcomponent_record.name == new_name

def test_create_subcomponent_folder_then_change_plugin_subcomponent(new_test_workspace: Path, rpp_home: Path, setup_plugins: LibraryManager) -> None:
    lm = setup_plugins
    # Create a new ComponentDataStore
    store = ComponentDataStore(new_test_workspace / "parts", lib_manager=lm)
    parent_record = store.create_component_folder("parent_component", "MockLib::MockControllerPlugin")
    parent_record_new, subcomponent_record = \
        store.create_subcomponent_folder(parent_record.folder,
                "subcomponent",
                "AwesomeSubcomponent",
                "MockLib::MockDisturbanceGeneratorPlugin")

    store.save_description(parent_record_new.folder, parent_record_new)
    store.save_description(subcomponent_record.folder, subcomponent_record)

    new_plugin_name = "MockLib::MockControllerPlugin"
    changed_subcomponent_record = \
        store.change_component_plugin_name(subcomponent_record.folder, new_plugin_name)

    assert changed_subcomponent_record is not None
    assert changed_subcomponent_record.folder.exists()
    assert changed_subcomponent_record.folder.is_dir()
    assert changed_subcomponent_record.plugin_name == new_plugin_name
    assert changed_subcomponent_record.name == "AwesomeSubcomponent"


def test_create_linked_subcomponent_folder_and_remove_linked_subcomponent(new_test_workspace: Path, rpp_home: Path, setup_plugins: LibraryManager) -> None:
    lm = setup_plugins
    # Create a new ComponentDataStore
    store = ComponentDataStore(new_test_workspace / "parts", lib_manager=lm)
    parent_record = store.create_component_folder("parent_component", "MockLib::MockControllerPlugin")
    child_record = store.create_component_folder("child_component", "MockLib::MockDisturbanceGeneratorPlugin")

    parent_record_new, linked_subcomponent_record = \
        store.create_linked_subcomponent_folder(parent_record,
                "linked_subcomponent",
                child_record)

    store.save_description(parent_record_new.folder, parent_record_new)
    store.save_description(linked_subcomponent_record.folder, linked_subcomponent_record)

    assert linked_subcomponent_record is not None
    assert linked_subcomponent_record.folder.exists()
    assert linked_subcomponent_record.folder.is_dir()
    assert linked_subcomponent_record.linked_component_id == child_record.id
    assert linked_subcomponent_record.name == "child_component"
    assert parent_record_new.subcomponents.get("linked_subcomponent") is not None

    store.remove_component_folder(linked_subcomponent_record.folder)

    assert not linked_subcomponent_record.folder.exists()
    assert child_record.folder.exists()  # The linked component's folder should still exist
    assert parent_record_new.folder.exists()