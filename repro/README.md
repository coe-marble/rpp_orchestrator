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
    python repro/link-into-empty-list-slot/repro.py

| Folder | Bug | Output on develop |
|---|---|---|
| parameter-set-undeclared | `ComponentParameterStore.save` accepts a name the plugin does not declare | `BUG: saved undeclared name 'cuont'` |
| parameters-bytecode-cache | `ComponentParameterStore.load` imports parameters.py and can read a stale bytecode cache | `BUG: ... 6 was read` |
| assign-filled-slot | assigning to a filled single slot raises | `BUG: ... raised TypeError` |
| config-copy-keeps-keys | `duplicate_script_configuration` drops keys other than `Components` | `BUG: 'Description' was lost` |
| link-into-empty-list-slot | linking a saved part into an empty list slot creates the link folder but the parent's `Subcomponents` never lists it | `BUG: links into an empty list slot are not stored in the parent` |

`link-into-empty-list-slot` also prints the names of the two links: both carry the name of the target, and `rpp ws component rename` refuses to rename a link, so two links to one part cannot get different names (see coe-marble/rpp_py#5).
