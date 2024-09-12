import sys
import pytest
import pathlib
import json

from understack_workflows.main.sync_server import get_args, get_ironic_node, update_ironic_node
from understack_workflows.node_configuration import IronicNodeConfiguration


def read_json_samples(file_path):
    here = pathlib.Path(__file__).parent
    ref = here.joinpath(file_path)
    with ref.open("r") as f:
        return f.read()


@pytest.fixture(autouse=True)
def mock_args(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["pytest",
                                      read_json_samples("json_samples/event-interface-update.json")])


@pytest.fixture
def fake_client(mocker):
    return mocker.patch("understack_workflows.ironic.client.IronicClient")


def get_ironic_node_state(fake_client, node_data):
    node = IronicNodeConfiguration.from_event(json.loads(read_json_samples("json_samples/event-interface-update.json")))

    ironic_node = get_ironic_node(node, fake_client)
    ironic_node.return_value = node_data

    return ironic_node.return_value['provision_state']


def test_args():
    var = get_args()
    assert var['data']['ip_addresses'][0]['host'] == "10.46.96.156"


def test_ironic_node_allowing_states(fake_client):
    ironic_node_state = get_ironic_node_state(fake_client,
                                              json.loads(read_json_samples(
                                                  "json_samples/ironic-enroll-node-data.json")))
    assert ironic_node_state in ["enroll", "manageable"]


def test_ironic_non_allowing_states(fake_client):
    ironic_node_state = get_ironic_node_state(fake_client,
                                              json.loads(read_json_samples(
                                                  "json_samples/ironic-active-node-data.json")))
    assert ironic_node_state not in ["enroll", "manageable"]


def test_update_ironic_node(fake_client):
    node = IronicNodeConfiguration.from_event(json.loads(read_json_samples("json_samples/event-interface-update.json")))
    drac_ip = json.loads(read_json_samples("json_samples/event-interface-update.json"))['data']["ip_addresses"][0]["host"]

    patches = [{'op': 'add', 'path': '/name', 'value': '1327198-GP2S.3.understack.iad3'},
               {'op': 'add', 'path': '/driver', 'value': 'idrac'},
               {'op': 'add',
                'path': '/driver_info/redfish_address',
                'value': 'https://10.46.96.156'},
               {'op': 'add', 'path': '/driver_info/redfish_verify_ca', 'value': False},
               {'op': 'remove', 'path': '/bios_interface'},
               {'op': 'remove', 'path': '/boot_interface'},
               {'op': 'remove', 'path': '/inspect_interface'},
               {'op': 'remove', 'path': '/management_interface'},
               {'op': 'remove', 'path': '/power_interface'},
               {'op': 'remove', 'path': '/vendor_interface'},
               {'op': 'remove', 'path': '/raid_interface'},
               {'op': 'remove', 'path': '/network_interface'}]
    update_ironic_node(node, drac_ip, fake_client)
    fake_client.update_node.assert_called_once_with(node.uuid, patches)
