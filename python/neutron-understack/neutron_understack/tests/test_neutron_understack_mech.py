import builtins
import json
import pathlib
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest


@dataclass
class ContextDouble:
    current: dict


def mock_context_data(filename):
    ref = pathlib.Path(__file__).parent / "fixtures" / filename
    with ref.open("r") as f:
        return ContextDouble(json.load(f))

@pytest.fixture
def mock_kubernetes_token():
    original_open = builtins.open
    with patch("builtins.open") as mock_open:

        def mock_open_function(file, *args, **kwargs):
            if file == "/run/secrets/kubernetes.io/serviceaccount/token":
                mock_file = MagicMock()
                mock_file.read.return_value = "abc"
                return mock_file
            return original_open(file, *args, **kwargs)

        mock_open.side_effect = mock_open_function
        yield mock_open


@patch("neutron_understack.argo.workflows.ArgoClient.submit")
def test_update_port_postcommit(mock_argo_client, mock_kubernetes_token):
    context_data = mock_context_data("neutron_update_port_postcommit.json")
    from neutron_understack.neutron_understack_mech import UnderstackDriver

    driver = UnderstackDriver()
    driver.update_port_postcommit(context_data)

    mock_argo_client.assert_called_once_with(
        template_name="undersync-device",
        entrypoint="trigger-undersync",
        parameters={
            "interface_mac": "fa:16:3e:35:1c:3d",
            "device_uuid": "",
            "network_name": "tenant",
            "dry_run": True,
            "force": False,
        },
        service_account="workflow",
    )
    mock_kubernetes_token.assert_called()
