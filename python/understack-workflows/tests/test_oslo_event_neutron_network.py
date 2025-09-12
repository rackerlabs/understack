import json
from unittest.mock import Mock

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
def network_delete_event_data():
    return _sample_fixture_data("oslo-event-network.delete.end")


@pytest.fixture
def mock_nautobot():
    nautobot = Mock()
    return nautobot


def test_handle_network_create(mock_nautobot, network_create_event_data):
    mock_nautobot.ipam.namespaces.create.return_value = "123"
    result = neutron_network.handle_network_create(
        None, mock_nautobot, network_create_event_data
    )

    mock_nautobot.ipam.namespaces.create.assert_called_once_with(
        name="5dddb3dc-b6d6-4247-a02e-8089c4374290"
    )
    assert result == 0


def test_handle_network_delete(mock_nautobot, network_delete_event_data):
    mock_nautobot.ipam.namespaces.delete.return_value = "123"

    result = neutron_network.handle_network_delete(
        None, mock_nautobot, network_delete_event_data
    )

    mock_nautobot.ipam.namespaces.delete.assert_called_once_with(
        {"name": "5dddb3dc-b6d6-4247-a02e-8089c4374290"}
    )
    assert result == 0
