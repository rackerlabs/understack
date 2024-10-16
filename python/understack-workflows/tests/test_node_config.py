import json
import pathlib
from unittest.mock import MagicMock

import pytest

from understack_workflows.ironic.client import IronicClient
from understack_workflows.node_configuration import IronicNodeConfiguration


@pytest.fixture
def interface_event() -> dict:
    here = pathlib.Path(__file__).parent
    ref = here.joinpath("json_samples/event-interface-update.json")
    with ref.open("r") as f:
        return json.load(f)


@pytest.fixture
def bmc_ip(interface_event: dict) -> str:
    return interface_event["data"]["ip_addresses"][0]["host"]


@pytest.fixture
def ironic_client() -> IronicClient:
    return MagicMock(spec_set=IronicClient)


@pytest.fixture
def mock_creds(mocker):
    mock = mocker.patch("understack_workflows.node_configuration.credential")
    mock.return_value = "ultra-secret credential value"
    return mock


def test_node_config_from_event_none_event():
    with pytest.raises(ValueError):
        _ = IronicNodeConfiguration.from_event({})


def test_node_config_from_event_interface_event(interface_event, bmc_ip, mock_creds):
    node = IronicNodeConfiguration.from_event(interface_event)
    assert node.uuid == interface_event["data"]["device"]["id"]
    assert node.name == interface_event["data"]["device"]["name"]
    assert node.driver == "idrac"
    assert node.driver_info.redfish_address == f"https://{bmc_ip}"
    assert node.driver_info.redfish_username == "root"
    mock_creds.assert_called_once_with("bmc_master", "key")


def test_node_create_from_event(interface_event, bmc_ip, ironic_client, mock_creds):
    node = IronicNodeConfiguration.from_event(interface_event)
    node.create_node(ironic_client)

    expected = {
        "uuid": node.uuid,
        "name": node.name,
        "driver": node.driver,
        "driver_info": {
            "redfish_address": f"https://{bmc_ip}",
            "redfish_verify_ca": False,
            "redfish_username": "root",
            "redfish_password": "Gzw/i8OD3ZabT7nH+sG1b0Eb",
        },
    }

    ironic_client.create_node.assert_called_once_with(expected)
