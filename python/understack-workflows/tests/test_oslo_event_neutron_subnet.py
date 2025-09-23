import json
from typing import cast
from unittest.mock import Mock

import pytest
from openstack.connection import Connection

from understack_workflows.oslo_event import neutron_subnet


def _sample_fixture_data(name: str) -> dict:
    """Load example event data from JSON fixture file."""
    with open(f"tests/json_samples/{name}.json") as f:
        data = json.loads(f.read())
    return json.loads(data["oslo.message"])


@pytest.fixture
def subnet_create_event_data():
    return _sample_fixture_data("oslo-event-subnet.create.end")


@pytest.fixture
def subnet_update_event_data():
    return _sample_fixture_data("oslo-event-subnet.update.end")


@pytest.fixture
def subnet_delete_event_data():
    return _sample_fixture_data("oslo-event-subnet.delete.end")


@pytest.fixture
def conn():
    return cast(Connection, None)


def test_handle_subnet_create(conn, subnet_create_event_data):
    mock_nautobot = Mock()
    mock_nautobot.ipam.namespaces.create.return_value = "123"

    result = neutron_subnet.handle_subnet_create_or_update(
        conn, mock_nautobot, subnet_create_event_data
    )

    mock_nautobot.ipam.prefixes.update.assert_called_once_with(
        id="eb9edeef-cc57-45ca-9caf-42be046822ff",
        data={
            "id": "eb9edeef-cc57-45ca-9caf-42be046822ff",
            "namespace": {
                "name": "b69b1a1d-5620-48fa-8fc2-fb0d1e90cf1c",
            },
            "prefix": "192.168.91.0/24",
            "status": "Active",
            "tenant": {
                "id": "3a69b984-6396-4e19-b295-f87cffa5db52",
            },
        },
    )
    assert result == 0


def test_handle_subnet_update(conn, subnet_update_event_data):
    mock_nautobot = Mock()
    mock_nautobot.ipam.namespaces.create.return_value = "123"

    result = neutron_subnet.handle_subnet_create_or_update(
        conn, mock_nautobot, subnet_update_event_data
    )

    mock_nautobot.ipam.prefixes.update.assert_called_once_with(
        id="1600eeef-6b3c-47fe-981a-e9ae83e23ce7",
        data={
            "id": "1600eeef-6b3c-47fe-981a-e9ae83e23ce7",
            "namespace": {
                "name": "f4aa4b99-2c2f-4698-a2f0-ac9920b1ee81",
            },
            "prefix": "10.148.4.32/27",
            "status": "Active",
            "tenant": {
                "id": "a4a74dbf-982a-471e-8150-db2babcac8c2",
            },
        },
    )
    assert result == 0


def test_handle_subnet_delete(conn, subnet_delete_event_data):
    mock_nautobot = Mock()
    mock_nautobot.ipam.prefixes.delete.return_value = [204]

    result = neutron_subnet.handle_subnet_delete(
        conn, mock_nautobot, subnet_delete_event_data
    )

    mock_nautobot.ipam.prefixes.delete.assert_called_once_with(
        ["eb9edeef-cc57-45ca-9caf-42be046822ff"]
    )
    assert result == 0
