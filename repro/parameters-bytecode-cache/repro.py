import os
import sys
import tempfile
from pathlib import Path

from rpp_orchestrator.component_storage import ComponentParameterStore

sys.dont_write_bytecode = False
folder = Path(tempfile.mkdtemp()) / "component"
store = ComponentParameterStore()
store.ensure_parameters_file(folder, {"count": 6})
path = store.parameters_path(folder)
modified = os.stat(path).st_mtime_ns
print("first read:", store.load(folder))
store.save(folder, {"count": 7})
# Same size and modification time, as a rewrite within one second looks to the cache.
os.utime(path, ns=(modified, modified))
value = store.load(folder)["count"]
print("second read:", value)
if value != 7:
    print("BUG: parameters.py contains count=7 but 6 was read")
    sys.exit(1)
print("OK")
