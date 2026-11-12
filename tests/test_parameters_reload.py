import os
import sys
from pathlib import Path

from rpp_orchestrator.component_storage import ComponentParameterStore


def test_rewrite_with_same_size_and_time_is_read_back(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(sys, "dont_write_bytecode", False)
    # An unchanged modification time and size is what a rewrite within the same
    # second looks like to the bytecode cache.
    store = ComponentParameterStore()
    component_folder = tmp_path / "component"
    store.ensure_parameters_file(component_folder, {"count": 6})
    params_path = store.parameters_path(component_folder)
    modified = os.stat(params_path).st_mtime_ns
    assert store.load(component_folder) == {"count": 6}

    store.save(component_folder, {"count": 7})
    os.utime(params_path, ns=(modified, modified))

    assert store.load(component_folder) == {"count": 7}
