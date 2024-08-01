import json
import pathlib

import pytest

from understack_workflows.node_configuration import IronicNodeConfiguration


@pytest.fixture
def interface_event() -> dict:
    here = pathlib.Path(__file__).parent
    ref = here.joinpath("json_samples/event-interface-update.json")
    with ref.open("r") as f:
        return json.load(f)


def test_node_config_from_event_none_event():
    with pytest.raises(ValueError):
        _ = IronicNodeConfiguration.from_event({})


def test_node_config_from_event_interface_event(interface_event):
    node = IronicNodeConfiguration.from_event(interface_event)
    assert node.uuid == interface_event["data"]["device"]["id"]
    assert node.name == interface_event["data"]["device"]["name"]
    assert node.driver == "redfish"
