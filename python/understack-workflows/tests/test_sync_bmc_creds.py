import sys
import pytest
import pathlib
import json

from understack_workflows.main.sync_bmc_creds import get_args
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
def fake_ironic_client(mocker):
    return mocker.patch("understack_workflows.ironic.client.IronicClient")


def get_ironic_node_state(fake_ironic_client, node_data):
    node = IronicNodeConfiguration.from_event(json.loads(read_json_samples("json_samples/event-interface-update.json")))

    ironic_node = fake_ironic_client.get_node(node.uuid)
    ironic_node.return_value = node_data

    return ironic_node.return_value['provision_state']


def test_args():
    var = get_args()
    assert var['data']['ip_addresses'][0]['host'] == "10.46.96.156"


def test_ironic_non_allowing_states(fake_ironic_client):
    ironic_node_state = get_ironic_node_state(fake_ironic_client,
                                              json.loads(read_json_samples(
                                                  "json_samples/ironic-active-node-data.json")))
    with pytest.raises(SystemExit) as sys_exit:
        if ironic_node_state not in ["enroll", "manageable"]:
            print('checking')
            sys.exit(0)
    assert sys_exit.value.code == 0


def test_ironic_node_allowing_states(fake_ironic_client):
    ironic_node_state = get_ironic_node_state(fake_ironic_client,
                                              json.loads(read_json_samples(
                                                  "json_samples/ironic-enroll-node-data.json")))
    assert ironic_node_state in ["enroll", "manageable"]
