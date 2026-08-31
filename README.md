# RPP Orchestrator

The orchestrator stores one script description per script in
`.rppws/script_descriptions/<script-name>.json`.

## Script configurations

Every script description must use the configuration-based format:

```json
{
    "ScriptPath": "/path/to/script.py",
    "Language": "python",
    "Configurations": {
        "Default": {
            "Components": {
                "controller": [
                    {
                        "Id": "component-id",
                        "PluginName": "library::Plugin"
                    }
                ]
            }
        }
    },
    "ActiveConfiguration": "Default",
    "Linked": false,
    "ScriptName": "controller",
    "ScriptLibrary": "workspace_library",
    "Spec": {
        "controller": "plugin_type::Controller"
    }
}
```

`ActiveConfiguration` must name an entry in `Configurations`. Each configuration
owns an independent `Components` mapping. Descriptions using the old top-level
`Components` field are not supported.

The workspace API supports creating, duplicating, renaming, deleting, and
activating configurations. A script must always retain at least one
configuration.

## GUI behavior

The left-side script tree contains configuration children. Selecting a
configuration displays and edits its assignments under **Configuration
Components**. Double-clicking a configuration activates it; the active
configuration is highlighted in green.

The contextual action group shows script actions when no configuration is
selected and configuration actions when a configuration is selected.
