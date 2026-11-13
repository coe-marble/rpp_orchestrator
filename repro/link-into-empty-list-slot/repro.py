import sys
import tempfile
from pathlib import Path

from rpp_orchestrator.workspace import ComponentRecord, Workspace

PLUGIN_TYPE = "rpp_testing::MotionController2D"
SPEC = {"actuators": f"List[{PLUGIN_TYPE}]"}


class Manager:
    def __init__(self, path):
        self.path = path

    def get_library_path(self, library_name):
        return str(self.path)

    def get_plugin_info_from_lib(self, plugin_name):
        return {"PluginMetadata": {"Components": SPEC}}


root = Path(tempfile.mkdtemp())
ws = Workspace(root, lib_manager=Manager(root))
ws.ensure_layout()
for name, spec in (("parent", SPEC), ("fin", {})):
    (root / name).mkdir()
    ws.part_records[name] = ComponentRecord(
        id=name, name=name, plugin_type=PLUGIN_TYPE, plugin_name="testlib::TestPlugin",
        library="testlib", folder=root / name, subcomponent_spec=dict(spec))

# Link the same saved part twice into the empty list slot.
ws.assign_subcomponent_to_parent("parent", "actuators", "fin")
ws.assign_subcomponent_to_parent("parent", "actuators", "fin")

stored = ws.read_part_descriptor(root / "parent").subcomponents.get("actuators", [])
links = [ws.read_part_descriptor(p.parent) for p in (root / "parent").rglob("description.json")
         if p.parent != root / "parent"]
print("links on disk:", len(links), "names:", [link.name for link in links])
print("parent lists in 'actuators':", len(stored))
if len(stored) != 2:
    print("BUG: links into an empty list slot are not stored in the parent")
    sys.exit(1)
print("OK")
