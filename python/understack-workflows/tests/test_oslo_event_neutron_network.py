import json
from unittest.mock import Mock

import pynautobot
import pytest

from understack_workflows.oslo_event import neutron_network


def _sample_fixture_data(name: str) -> dict:
    """Load example event data from JSON fixture file."""
    with open(f"tests/json_samples/{name}.json") as f:
        data = json.loads(f.read())
    return json.loads(data["oslo.message"])


@pytest.fixture
def network_create_event_data():
    return _sample_fixture_data("oslo-event-network.create.end")


@pytest.fixture
def network_update_event_data():
    return _sample_fixture_data("oslo-event-network.update.end")


@pytest.fixture
def network_delete_event_data():
    return _sample_fixture_data("oslo-event-network.delete.end")


def test_handle_network_create(network_create_event_data):
    mock_nautobot = Mock()
    mock_nautobot.ipam.namespaces.create.return_value = "123"

    result = neutron_network.handle_network_create_or_update(
        None, mock_nautobot, network_create_event_data, ucvni_group_name="FOO"
    )

    mock_nautobot.ipam.namespaces.create.assert_called_once_with(
        name="5dddb3dc-b6d6-4247-a02e-8089c4374290"
    )
    mock_nautobot.plugins.undercloud_vni.ucvnis.create.assert_called_once_with(
        {
            "id": "5dddb3dc-b6d6-4247-a02e-8089c4374290",
            "name": "marek-storage-test-network",
            "status": {
                "name": "Active",
            },
            "tenant": "46c1e917-980e-4485-915b-1444e8c50cc2",
            "ucvni_group": {
                "name": "FOO",
            },
            "ucvni_id": 1862,
        },
    )
    assert result == 0


def test_handle_network_update(network_update_event_data):
    mock_nautobot = Mock()
    mock_nautobot.ipam.namespaces.update.return_value = "123"

    result = neutron_network.handle_network_create_or_update(
        None, mock_nautobot, network_update_event_data, ucvni_group_name="FOO"
    )

    mock_nautobot.ipam.namespaces.create.assert_called_once_with(
        name="f4aa4b99-2c2f-4698-a2f0-ac9920b1ee81"
    )
    mock_nautobot.plugins.undercloud_vni.ucvnis.create.assert_called_once_with(
        {
            "id": "f4aa4b99-2c2f-4698-a2f0-ac9920b1ee81",
            "name": "service-net",
            "status": {
                "name": "Active",
            },
            "tenant": "a4a74dbf-982a-471e-8150-db2babcac8c2",
            "ucvni_group": {
                "name": "FOO",
            },
            "ucvni_id": 1860,
        },
    )
    assert result == 0


def test_handle_network_create_idempotent_namespace(network_create_event_data):
    mock_pynautobot_req = Mock()
    mock_pynautobot_req.status_code = 400
    mock_pynautobot_req.text = "namespace with this name already exists"

    mock_nautobot = Mock()
    mock_nautobot.ipam.namespaces.create.side_effect = pynautobot.RequestError(
        mock_pynautobot_req
    )

    result = neutron_network.handle_network_create_or_update(
        None, mock_nautobot, network_create_event_data, ucvni_group_name="FOO"
    )
    assert result == 0


def test_handle_network_create_idempotent_ucvni(network_create_event_data):
    mock_nautobot = Mock()
    mock_nautobot.ipam.namespaces.create.return_value = "123"

    mock_pynautobot_req = Mock()
    mock_pynautobot_req.status_code = 400
    mock_pynautobot_req.text = "this Id already exists"

    mock_nautobot.plugins.undercloud_vni.ucvnis.create.side_effect = (
        pynautobot.RequestError(mock_pynautobot_req)
    )

    result = neutron_network.handle_network_create_or_update(
        None, mock_nautobot, network_create_event_data, ucvni_group_name="FOO"
    )
    assert result == 0


def test_handle_network_delete(network_delete_event_data):
    mock_nautobot_namespace = Mock()
    mock_nautobot_namespace.delete.return_value = "123"

    mock_nautobot_prefix = Mock()
    mock_nautobot_prefix.delete.return_value = "123"

    mock_nautobot = Mock()
    mock_nautobot.ipam.namespaces.get.return_value = mock_nautobot_namespace
    mock_nautobot.ipam.prefixes.filter.return_value = [mock_nautobot_prefix]

    result = neutron_network.handle_network_delete(
        None, mock_nautobot, network_delete_event_data
    )

    mock_nautobot.ipam.namespaces.get.assert_called_once_with(
        name="5dddb3dc-b6d6-4247-a02e-8089c4374290"
    )
    mock_nautobot_namespace.delete.assert_called_once()
    mock_nautobot.plugins.undercloud_vni.ucvnis.delete.assert_called_once_with(
        ["5dddb3dc-b6d6-4247-a02e-8089c4374290"]
    )
    mock_nautobot_prefix.delete.assert_called_once()
    assert result == 0
