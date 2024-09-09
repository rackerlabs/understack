from dataclasses import dataclass
from unittest.mock import patch, MagicMock
import pytest
from neutron_understack.argo.workflows import ArgoClient

from neutron_understack.neutron_understack_mech import UnderstackDriver

# TODO: I am not sure how we run tests in this project.

@dataclass
class ContextDouble:
  current: dict

def mock_context_data(file):
    ref = pathlib.Path(__file__).joinpath(filename)
    with ref.open("r") as f:
        return ContextDouble(json.load(f))

@patch('neutron_understack.argo.workflows.ArgoClient')
def test_update_port_postcommit(mock_argo_client):
    context_data = mock_context_data(
        "fixtures/neutron_update_port_postcommit.json"
    )

    UnderstackDriver.update_port_postcommit(context_data)

    mock_argo_client.assert_called_once_with(
        template_name="undersync-device",
        entrypoint="trigger-undersync",
        parameters={
            "interface_uuid": "e5d5cd73-ca9a-4b74-9d52-43188d0cdcaa",
            "device_uuid": "41d18c6a-5548-4ee9-926f-4e3ebf43153f",
            "network_name": "provisioning",
            "dry_run": false,
            "force": false,
        },
    )
