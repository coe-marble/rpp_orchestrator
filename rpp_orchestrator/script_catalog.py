from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import TYPE_CHECKING

from rpp_plugin_registrator.library_manager import LibraryManager

from .script_handle import SCRIPT_LANGUAGES, get_script_language_from_path

if TYPE_CHECKING:
    from .workspace import Workspace


@dataclass(frozen=True)
class RegisteredScript:
    script_name: str
    name: str
    library: str
    path: Path
    language: str


class ScriptCatalog:
    """Discovers scripts from currently registered libraries on demand."""

    script_descriptions_path = Path(".rppws") / "script_descriptions"

    def __init__(self, library_manager: LibraryManager) -> None:
        self.library_manager = library_manager

    def list_registered_scripts(
        self,
        exclude_library: str | None = None,
        workspace: Workspace | None = None,
    ) -> list[RegisteredScript]:
        scripts: list[RegisteredScript] = []
        linked_libraries = set()
        if workspace is not None:
            linked_libraries = {
                description.get("ScriptLibrary")
                for script_handle in workspace.list_scripts()
                for description in [script_handle.load_description()]
                if description.get("Linked") and description.get("ScriptLibrary")
            }
        for library in self.library_manager.list_plugin_libraries():
            library_name = library["Name"]
            if library_name == exclude_library or library_name in linked_libraries:
                continue
            scripts.extend(self.list_library_scripts(library_name))
        return sorted(scripts, key=lambda script: (script.library, script.script_name))

    def list_library_scripts(self, library_name: str) -> list[RegisteredScript]:
        library_path_text = self.library_manager.get_library_path(library_name)
        if library_path_text is None:
            return []
        library_path = Path(library_path_text).resolve()
        supported_extensions = {
            language.extension for language in SCRIPT_LANGUAGES.values()
        }
        scripts: list[RegisteredScript] = []
        descriptions_path = library_path / self.script_descriptions_path
        if not descriptions_path.is_dir():
            return scripts

        for description_path in sorted(descriptions_path.glob("*.json")):
            if not description_path.is_file():
                continue
            description = json.loads(description_path.read_text(encoding="utf-8"))
            script_path_value = description.get("ScriptPath")
            if not isinstance(script_path_value, str):
                continue
            script_path = Path(script_path_value).expanduser().resolve()
            if not script_path.is_file() or script_path.suffix not in supported_extensions:
                continue
            script_name = description.get("ScriptName", script_path.stem)
            if not isinstance(script_name, str):
                script_name = script_path.stem
            scripts.append(RegisteredScript(
                script_name=f"{library_name}::{script_name}",
                name=script_name,
                library=library_name,
                path=script_path,
                language=get_script_language_from_path(script_path),
            ))
        return scripts
