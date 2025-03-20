from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from neutron_understack.nautobot import Nautobot
from neutron_understack.nautobot import VlanPayload


@pytest.fixture
def mock_pynautobot_api():
    with patch("neutron_understack.nautobot.pynautobot.api") as mock_api:
        mock_ipam = MagicMock()
        mock_ipam.vlans.delete = MagicMock()
        mock_ipam.vlans.create = MagicMock()

        mock_api.return_value.ipam = mock_ipam

        yield mock_api, mock_ipam


@pytest.fixture
def nautobot(mock_pynautobot_api):
    return Nautobot(nb_url="http://fake-nautobot", nb_token="fake-token")  # noqa: S106


def test_delete_vlan(nautobot, mock_pynautobot_api):
    _, mock_ipam = mock_pynautobot_api
    vlan_id = "123"

    nautobot.delete_vlan(vlan_id)

    mock_ipam.vlans.delete.assert_called_once_with([vlan_id])


def test_create_vlan_and_associate_vlan_to_ucvni(nautobot, mock_pynautobot_api):
    _, mock_ipam = mock_pynautobot_api

    payload = VlanPayload(
        id="vlan-123",
        vid=101,
        vlan_group_name="test-group",
        network_id="net-456",
    )

    expected_payload_dict = {
        "id": "vlan-123",
        "vid": 101,
        "vlan_group": {"name": "test-group"},
        "name": "test-network",
        "status": {"name": "Active"},
        "relationships": {"ucvni_vlans": {"source": {"objects": [{"id": "net-456"}]}}},
    }

    payload.to_dict = lambda: expected_payload_dict

    nautobot.create_vlan_and_associate_vlan_to_ucvni(payload)

    mock_ipam.vlans.create.assert_called_once_with(expected_payload_dict)
