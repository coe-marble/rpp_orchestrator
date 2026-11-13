# Reproductions for rpp_orchestrator

One folder per bug under `repro/`. Each `repro.py` prints `BUG: ...` and exits 1 when the
bug is present, and prints `OK` (exit 0) otherwise. They need only `rpp_orchestrator` and
its dependencies to be importable (the CI container with the packages installed as in
`.github/workflows/ci.yml`), no workspace on disk.

Run from the repository root of the checkout under test:

    python repro/parameter-set-undeclared/repro.py
    python repro/parameters-bytecode-cache/repro.py
    python repro/assign-filled-slot/repro.py
    python repro/config-copy-keeps-keys/repro.py

| Folder | Bug | Output on develop |
|---|---|---|
| parameter-set-undeclared | `ComponentParameterStore.save` accepts a name the plugin does not declare | `BUG: saved undeclared name 'cuont'` |
| parameters-bytecode-cache | `ComponentParameterStore.load` imports parameters.py and can read a stale bytecode cache | `BUG: ... 6 was read` |
| assign-filled-slot | assigning to a filled single slot raises | `BUG: ... raised TypeError` |
| config-copy-keeps-keys | `duplicate_script_configuration` drops keys other than `Components` | `BUG: 'Description' was lost` |
