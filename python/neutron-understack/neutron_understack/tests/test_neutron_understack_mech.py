from unittest.mock import MagicMock

import pytest

from neutron_understack.neutron_understack_mech import UnderstackDriver
from neutron_understack.argo.workflows import ArgoClient


@pytest.fixture
def argo_client() -> ArgoClient:
    return MagicMock(spec_set=ArgoClient)


def test_move_to_network__provisioning(argo_client):
    driver = UnderstackDriver()
    driver._move_to_network(
        vif_type="other",
        mac_address="fa:16:3e:35:1c:3d",
        device_uuid="41d18c6a-5548-4ee9-926f-4e3ebf43153f",
        network_id="c2702769-5592-4555-8ae6-e670db82c31e",
        argo_client=argo_client,
    )

    argo_client.submit.assert_called_once_with(
        template_name="undersync-device",
        entrypoint="trigger-undersync",
        parameters={
            "interface_mac": "fa:16:3e:35:1c:3d",
            "device_uuid": "41d18c6a-5548-4ee9-926f-4e3ebf43153f",
            "network_name": "tenant",
            "network_id": "c2702769-5592-4555-8ae6-e670db82c31e",
            "dry_run": True,
            "force": False,
        },
        service_account="workflow",
    )
