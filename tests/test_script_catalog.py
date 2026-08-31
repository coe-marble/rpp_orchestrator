from pathlib import Path

from rpp_orchestrator.script_catalog import ScriptCatalog


class FakeLibraryManager:
    def __init__(self, libraries: dict[str, Path]) -> None:
        self.libraries = libraries

    def list_plugin_libraries(self):
        return [
            {"Name": name, "Path": str(path)}
            for name, path in self.libraries.items()
        ]

    def get_library_path(self, library_name: str):
        path = self.libraries.get(library_name)
        return str(path) if path is not None else None


class FakeScriptHandle:
    def __init__(self, description: dict[str, str]) -> None:
        self.description = description

    def load_description(self):
        return self.description


class FakeWorkspace:
    def __init__(self, script_handles: list[FakeScriptHandle]) -> None:
        self.script_handles = script_handles

    def list_scripts(self):
        return self.script_handles


def test_catalog_discovers_scripts_from_other_registered_libraries(tmp_path: Path):
    current_library = tmp_path / "current"
    other_library = tmp_path / "other"
    (current_library / ".rppws" / "script_descriptions").mkdir(parents=True)
    descriptions_path = other_library / ".rppws" / "script_descriptions"
    descriptions_path.mkdir(parents=True)
    controller_cpp = other_library / "controller.cpp"
    controller_py = other_library / "nested" / "controller.py"
    controller_cpp.write_text("", encoding="utf-8")
    controller_py.parent.mkdir(parents=True)
    controller_py.write_text("", encoding="utf-8")
    (descriptions_path / "controller.json").write_text(
        '{"ScriptPath": "' + str(controller_cpp) + '", "ScriptName": "controller"}',
        encoding="utf-8",
    )
    (descriptions_path / "nested-controller.json").write_text(
        '{"ScriptPath": "' + str(controller_py) + '", "ScriptName": "nested/controller"}',
        encoding="utf-8",
    )
    (descriptions_path / "notes.json").write_text(
        '{"ScriptPath": "' + str(other_library / "notes.txt") + '"}',
        encoding="utf-8",
    )

    catalog = ScriptCatalog(FakeLibraryManager({
        "current": current_library,
        "other": other_library,
    }))

    scripts = catalog.list_registered_scripts(exclude_library="current")

    assert [script.script_name for script in scripts] == [
        "other::controller",
        "other::nested/controller",
    ]
    assert [script.language for script in scripts] == ["cpp", "python"]


def test_catalog_excludes_already_linked_libraries(tmp_path: Path):
    library = tmp_path / "library"
    descriptions_path = library / ".rppws" / "script_descriptions"
    descriptions_path.mkdir(parents=True)
    script_path = library / "controller.py"
    script_path.write_text("", encoding="utf-8")
    (descriptions_path / "controller.json").write_text(
        '{"ScriptPath": "' + str(script_path) + '", "ScriptName": "controller"}',
        encoding="utf-8",
    )

    catalog = ScriptCatalog(FakeLibraryManager({"library": library}))
    workspace = FakeWorkspace([
        FakeScriptHandle({"Linked": True, "ScriptLibrary": "library"}),
    ])

    assert catalog.list_registered_scripts(workspace=workspace) == []
