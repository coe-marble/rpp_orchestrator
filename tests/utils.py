from pathlib import Path
from typing import Generator
from rpp_plugin_registrator.library_manager import LibraryManager
from rpp_orchestrator.workspace import create_workspace


def setup_test_plugins(rpp_home) -> LibraryManager:


    manager = LibraryManager(rpp_home=rpp_home)
    handle = manager.get_or_create_plugin_library("MockLib")

    controller_source = Path(handle.path) / handle.name / "MockControllerPlugin.py"
    controller_source.write_text(
        "\n".join(
            [
                "from rpp_plugin_types.rpp_testing import MotionController2D",
                "",
                "",
                "class MockControllerPlugin(MotionController2D):",
                "    tag = \"mock_ctl\"",
                "",
                "    def name(self) -> str:",
                "        return \"MockControllerPlugin\"",
                "",
                "    def execute(self, input):",
                "        return input",
                "",
            ]
        ),
        encoding="utf-8",
    )

    disturbance_source = Path(handle.path) / handle.name / "MockDisturbanceGeneratorPlugin.py"
    disturbance_source.write_text(
        "\n".join(
            [
                "from rpp_plugin_types.rpp_testing import DisturbanceGenerator2D",
                "from rpp_py.plugin import ParameterDescription",
                "class MockDisturbanceGeneratorPlugin(DisturbanceGenerator2D):",
                "    PARAMETERS = [",
                "        ParameterDescription(name=\"param1\", default_value=0.0),",
                "        ParameterDescription(name=\"param2\", default_value=1.0),",
                "        ParameterDescription(name=\"param3\", default_value=True),",
                "    ]",
                "    tag = \"mock_dist\"",
                "",
                "    def name(self) -> str:",
                "        return \"MockDisturbanceGeneratorPlugin\"",
                "",
                "    def on_step(self, y, dt):",
                "        return y",
                "",
            ]
        ),
        encoding="utf-8",
    )

    controller_with_single_component_source = Path(handle.path) / handle.name / "MockControllerWithSingleComponentPlugin.py"
    controller_with_single_component_source.write_text(
        "\n".join(
            [
                "from rpp_plugin_types.rpp_testing import MotionController2D",
                "",
                "",
                "class MockControllerWithSingleComponentPlugin(MotionController2D):",
                "    COMPONENTS = {",
                "        \"ctl1\": \"rpp_testing::MotionController2D\",",
                "    }",
                "",
                "    def name(self) -> str:",
                "        return \"MockControllerWithSingleComponentPlugin\"",
                "",
                "    def execute(self, input):",
                "        return input",
                "",
            ]
        ),
    )

    controller_with_multiple_components_source = Path(handle.path) / handle.name / "MockControllerWithMultipleComponentsPlugin.py"
    controller_with_multiple_components_source.write_text(
        "\n".join(
            [
                "from rpp_plugin_types.rpp_testing import MotionController2D",
                "",
                "",
                "class MockControllerWithMultipleComponentsPlugin(MotionController2D):",
                "    COMPONENTS = {",
                "        \"ctl1\": \"rpp_testing::MotionController2D\",",
                "        \"ctl2\": \"rpp_testing::MotionController2D\",",
                "    }",
                "",
                "    def name(self) -> str:",
                "        return \"MockControllerWithMultipleComponentsPlugin\"",
                "",
                "    def execute(self, input):",
                "        return input",
                "",
            ]
        ),
    )

    controller_with_single_component_list_source = Path(handle.path) / handle.name / "MockControllerWithSingleComponentListPlugin.py"
    controller_with_single_component_list_source.write_text(
        "\n".join(
            [
                "from rpp_plugin_types.rpp_testing import MotionController2D",
                "",
                "",
                "class MockControllerWithSingleComponentListPlugin(MotionController2D):",
                "    COMPONENTS = {",
                "        \"ctl1\": [\"rpp_testing::MotionController2D\"],",
                "    }",
                "",
                "    def name(self) -> str:",
                "        return \"MockControllerWithSingleComponentListPlugin\"",
                "",
                "    def execute(self, input):",
                "        return input",
                "",
            ]
        ),
    )


    manager.register_plugin_from_source(controller_source, "MockLib")
    manager.register_plugin_from_source(disturbance_source, "MockLib")
    manager.register_plugin_from_source(controller_with_single_component_source, "MockLib")
    manager.register_plugin_from_source(controller_with_multiple_components_source, "MockLib")
    manager.register_plugin_from_source(controller_with_single_component_list_source, "MockLib")
    return manager


def create_mock_workspace(tmp_path: Path, rpp_home: Path) -> Path:
    workspace = create_workspace(tmp_path / "mock_workspace", name="mock_workspace", overwrite=True)
    parent_record = workspace.create_component(
        component_name="parent_component",
        plugin_name="MockLib::MockControllerWithSingleComponentPlugin",
    )
    component2_record = workspace.create_component(
        component_name="component2",
        plugin_name="MockLib::MockControllerPlugin",
    )
    child_record = workspace.create_subcomponent(
        parent_folder=parent_record.folder,
        slot_name="ctl1",
        component_name="subcomponent1",
        plugin_name="MockLib::MockControllerPlugin",
    )

    parent2_record = workspace.create_component(
        component_name="parent2_component",
        plugin_name="MockLib::MockControllerWithMultipleComponentsPlugin",
    )

    parent3_record = workspace.create_component(
        component_name="parent3_component",
        plugin_name="MockLib::MockControllerWithSingleComponentListPlugin",
    )

    parent2_child1_record = workspace.create_subcomponent(
        parent_folder=parent2_record.folder,
        slot_name="ctl1",
        component_name="parent2_child1",
        plugin_name="MockLib::MockControllerPlugin",
    )

    parent2_child2_record = workspace.create_subcomponent(
        parent_folder=parent2_record.folder,
        slot_name="ctl2",
        component_name="parent2_child2",
        plugin_name="MockLib::MockControllerPlugin",
    )

    parent3_child1_record = workspace.create_subcomponent(
        parent_folder=parent3_record.folder,
        slot_name="ctl1",
        component_name="parent3_child1",
        plugin_name="MockLib::MockControllerPlugin",
    )

    parent3_child2_record = workspace.create_subcomponent(
        parent_folder=parent3_record.folder,
        slot_name="ctl1",
        component_name="parent3_child2",
        plugin_name="MockLib::MockControllerWithSingleComponentPlugin",
    )

    child_of_child_record = workspace.create_subcomponent(
        parent_folder=parent3_child2_record.folder,
        slot_name="ctl1",
        component_name="child_of_child",
        plugin_name="MockLib::MockControllerPlugin",
    )

    workspace.create_script(
        script_path_or_name="example.py", source=example_source()
    )

    return workspace



def example_source() -> str:
    return """
from __future__ import annotations

from rpp_orchestrator.orchestration_script import OrchestrationScript

from rpp_plugin_types.rpp_testing import MotionController2D
from rpp_plugin_types.rpp_testing import DisturbanceGenerator2D



class Example(OrchestrationScript):
    COMPONENTS = {
        "ctl_main": "rpp_testing::MotionController2D",
        "ctl_disturbance": "rpp_testing::DisturbanceGenerator2D",
    }
    def run(self) -> None:
        raise NotImplementedError("Define the workspace logic here.")


    """