import tempfile
from pathlib import Path
from typing import Generator
import pytest

import rpp_plugin_registrator.registry_paths as rp
from rpp_plugin_registrator.library_manager import LibraryManager
from rpp_orchestrator.component_storage import ComponentDataStore

from tests.utils import setup_test_plugins


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

@pytest.fixture
def mock_workspace_root():
    tests_dir = Path(__file__).parent
    return tests_dir / "mock_workspace"

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
