import sys
import tempfile
from pathlib import Path

from rpp_orchestrator.workspace import Workspace


class Manager:
    def __init__(self, path):
        self.path = path

    def get_library_path(self, library_name):
        return str(self.path)


root = Path(tempfile.mkdtemp())
ws = Workspace(root, lib_manager=Manager(root))
ws.ensure_layout()
script = ws.create_script("main")
description = ws.read_script_description(script.path)
description["Configurations"]["Default"]["Description"] = "one toy system"
ws._write_script_description_payload(description, script.path)
ws.duplicate_script_configuration(script, "Default", "Copied")
copied = ws.read_script_description(script.path)["Configurations"]["Copied"]
print("keys of copy:", sorted(copied))
if "Description" not in copied:
    print("BUG: 'Description' was lost in the copy")
    sys.exit(1)
print("OK")
