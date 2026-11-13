import sys
import tempfile
from pathlib import Path

from rpp_orchestrator.workspace import ComponentRecord, Workspace

PLUGIN_TYPE = "rpp_testing::MotionController2D"


class Manager:
    def __init__(self, path):
        self.path = path

    def get_library_path(self, library_name):
        return str(self.path)


root = Path(tempfile.mkdtemp())
ws = Workspace(root, lib_manager=Manager(root))
ws.ensure_layout()
for name in ("first", "second"):
    ws.part_records[name] = ComponentRecord(
        id=name, name=name, plugin_type=PLUGIN_TYPE, plugin_name="testlib::TestPlugin",
        library="testlib", folder=root / name, subcomponent_spec={})
script = ws.create_script("main")
script.add_component_slot("ctl_main", PLUGIN_TYPE)  # single slot
ws.assign_component_to_script(script, "ctl_main", "first")
try:
    ws.assign_component_to_script(script, "ctl_main", "second")
except Exception as error:
    print("BUG: assigning into the filled single slot raised", type(error).__name__, error)
    sys.exit(1)
ids = [i["Id"] for i in ws.active_script_components(ws.read_script_description(script.path))["ctl_main"]]
print("slot holds:", ids)
sys.exit(0 if ids == ["second"] else 1)
