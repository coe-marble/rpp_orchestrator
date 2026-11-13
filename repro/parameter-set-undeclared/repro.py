import shutil
import sys
import tempfile
from pathlib import Path

from rpp_orchestrator.component_storage import ComponentParameterStore


class Manager:
    def get_plugin_info_from_lib(self, plugin_name):
        return {"PluginMetadata": {"Parameters": {
            "count": {"name": "count", "type": "int", "default_value": 3}}}}


folder = Path(tempfile.mkdtemp()) / "component"
folder.mkdir()
shutil.copy(Path(__file__).with_name("description.json"), folder)
store = ComponentParameterStore(lib_manager=Manager())
try:
    store.save(folder, {"cuont": 5})  # mistyped name, the plugin declares "count"
except ValueError as error:
    print("OK: refused:", error)
    sys.exit(0)
print("BUG: saved undeclared name 'cuont':", store.load(folder))
sys.exit(1)
