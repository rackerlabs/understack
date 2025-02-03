import json
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from neutron_understack.nautobot import Nautobot
from neutron_understack.neutron_understack_mech import UnderstackDriver
from neutron_understack.undersync import Undersync


@pytest.fixture
def current_context() -> dict:
    file_path = "neutron_understack/tests/fixtures/neutron_update_port_postcommit.json"
    with open(file_path) as context_file:
        return json.load(context_file)


@pytest.fixture
def context(current_context) -> MagicMock:
    return MagicMock(current=current_context)


@pytest.fixture
def nautobot_client() -> Nautobot:
    return MagicMock(spec_set=Nautobot)


@pytest.fixture
def undersync_client() -> Undersync:
    return MagicMock(spec_set=Undersync)


driver = UnderstackDriver()


def test_fetch_connected_interface_uuid(context):
    result = driver.fetch_connected_interface_uuid(context.current)
    assert result == "03921f8d-b4de-412e-a733-f8eade4c6268"


def test_fail_fetch_connected_interface_uuid(context):
    context.current["binding:profile"]["local_link_information"][0]["port_id"] = 11
    with pytest.raises(ValueError):
        driver.fetch_connected_interface_uuid(context)


def test_update_nautobot_for_tenant_network(nautobot_client):
    driver.nb = nautobot_client
    attrs = {
        "prep_switch_interface.return_value": {
            "vlan_group_id": "304bd384-338a-4365-9394-0c356ec698ed"
        }
    }
    nautobot_client.configure_mock(**attrs)
    driver.update_nautobot("111", "222", 333)

    nautobot_client.prep_switch_interface.assert_called_once_with(
        connected_interface_id="222", ucvni_uuid="111", vlan_tag=333
    )


def test_update_nautobot_for_provisioning_network(nautobot_client):
    attrs = {
        "configure_port_status.return_value": {"device": {"id": "444"}},
        "fetch_vlan_group_uuid.return_value": "304bd384-338a-4365-9394-0c356ec698ed",
    }
    nautobot_client.configure_mock(**attrs)
    driver.nb = nautobot_client
    driver.update_nautobot("change_me", "333", 123)

    nautobot_client.configure_port_status.assert_called_once_with(
        "333", "Provisioning-Interface"
    )
    nautobot_client.fetch_vlan_group_uuid.assert_called_once_with("444")


@patch("neutron_understack.neutron_understack_mech.UnderstackDriver.update_nautobot")
@patch(
    "neutron_understack.neutron_understack_mech.UnderstackDriver.fetch_connected_interface_uuid"
)
def test_success_update_port_post_commit(
    mocked_update_nautobot,
    mocked_fetch_connected_interface_uuid,
    context,
    undersync_client,
):
    driver.undersync = undersync_client
    driver.update_port_postcommit(context)

    mocked_fetch_connected_interface_uuid.assert_called_once()
    mocked_update_nautobot.assert_called_once()
    undersync_client.sync_devices.assert_called_once()


@patch(
    "neutron_understack.neutron_understack_mech.UnderstackDriver.fetch_connected_interface_uuid"
)
def test_wrong_vif_type_update_port_post_commit(
    mocked_fetch_connected_interface_uuid, context
):
    context.current["binding:vif_type"] = "unbound"
    driver.update_port_postcommit(context)

    mocked_fetch_connected_interface_uuid.assert_not_called()


def test_create_subnet_postcommit_private(nautobot_client):
    context = MagicMock(
        current={
            "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "network_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            "cidr": "1.0.0.0/24",
            "router:external": False,
        }
    )

    driver.nb = nautobot_client
    driver.create_subnet_postcommit(context)

    nautobot_client.subnet_create.assert_called_once_with(
        "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "1.0.0.0/24",
        "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    )


def test_create_subnet_postcommit_public(nautobot_client, undersync_client):
    context = MagicMock(
        current={
            "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "network_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            "cidr": "1.0.0.0/24",
            "router:external": True,
        }
    )

    nautobot_client.get_switchport_vlan_details.return_value = [
        "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        666,
        "cccccccc-cccc-cccc-cccc-cccccccccccc",
    ]

    driver.nb = nautobot_client
    driver.undersync = undersync_client

    driver.create_subnet_postcommit(context)

    nautobot_client.subnet_create.assert_called_once_with(
        "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "1.0.0.0/24", "Global"
    )

    nautobot_client.interface_create.assert_called_once_with(
        device="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", name="Vlan666"
    )
    nautobot_client.ip_address_create.assert_called_once_with(
        cidr="1.0.0.1", namespace="Global"
    )
    nautobot_client.add_ip_to_interface.assert_called_once()
    undersync_client.sync_devices.assert_called_once_with(
        vlan_group_uuids="cccccccc-cccc-cccc-cccc-cccccccccccc", dry_run=True
    )


def test_delete_subnet_postcommit_public(nautobot_client, undersync_client):
    context = MagicMock(
        current={
            "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "network_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            "cidr": "1.0.0.0/24",
            "router:external": True,
        }
    )

    nautobot_client.subnet_cascade_delete.return_value = [
        "cccccccc-cccc-cccc-cccc-cccccccccccc"
    ]
    driver.nb = nautobot_client
    driver.undersync = undersync_client

    driver.delete_subnet_postcommit(context)

    nautobot_client.subnet_cascade_delete.assert_called_once_with(
        "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    )

    undersync_client.sync_devices.assert_called_once_with(
        vlan_group_uuids="cccccccc-cccc-cccc-cccc-cccccccccccc", dry_run=True
    )
