from unittest.mock import MagicMock

import pytest

from neutron_understack.argo.workflows import ArgoClient
from neutron_understack.neutron_understack_mech import UnderstackDriver


@pytest.fixture
def argo_client() -> ArgoClient:
    return MagicMock(spec_set=ArgoClient)


def test_move_to_network__provisioning(argo_client, device_id, network_id, mac_address):
    driver = UnderstackDriver()
    driver._move_to_network(
        vif_type="other",
        mac_address=mac_address,
        device_uuid=str(device_id),
        network_id=str(network_id),
        argo_client=argo_client,
    )

    argo_client.submit.assert_called_once_with(
        template_name="undersync-device",
        entrypoint="trigger-undersync",
        parameters={
            "interface_mac": mac_address,
            "device_uuid": str(device_id),
            "network_name": "tenant",
            "network_id": str(network_id),
            "dry_run": True,
            "force": False,
        },
        service_account="workflow",
    )
