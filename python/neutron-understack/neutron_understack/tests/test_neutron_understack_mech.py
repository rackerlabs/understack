import json
from copy import deepcopy
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
def original_context(current_context) -> dict:
    original = deepcopy(current_context)
    return original


@pytest.fixture
def context(current_context, original_context) -> MagicMock:
    return MagicMock(
        current=current_context,
        original=original_context,
        original_vif_type=original_context["binding:vif_type"],
        vif_type=current_context["binding:vif_type"],
    )


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


@patch("neutron_understack.neutron_understack_mech.UnderstackDriver.update_nautobot")
@patch("neutron_understack.utils.fetch_subport_network_id", return_value="112233")
def test_update_port_post_commit_when_trunk_details_are_present(
    mocked_update_nautobot,
    mocked_fetch_subport_network_id,
    nautobot_client,
    context,
):
    context.current["trunk_details"] = {
        "trunk_id": "11223344",
        "sub_ports": [
            {"port_id": "aabbcc"},
        ],
    }
    driver.nb = nautobot_client
    driver.update_port_postcommit(context)
    nautobot_client.prep_switch_interface.assert_called_once_with(
        connected_interface_id="03921f8d-b4de-412e-a733-f8eade4c6268",
        ucvni_uuid="112233",
        modify_native_vlan=False,
        vlan_tag=None,
    )


@patch("neutron_understack.utils.fetch_subport_network_id", return_value="112233")
def test_delete_tenant_port_on_unbound_when_trunk_details_are_present(
    nautobot_client,
    context,
):
    context.current["trunk_details"] = {
        "trunk_id": "11223344",
        "sub_ports": [
            {"port_id": "aabbcc"},
        ],
    }
    context.vif_type = "unbound"
    context.original_vif_type = "other"
    attrs = {"detach_port.return_value": "304bd384-338a-4365-9394-0c356ec698ed"}
    nautobot_client.configure_mock(**attrs)
    driver.nb = nautobot_client
    driver._delete_tenant_port_on_unbound(context)
    nautobot_client.detach_port.assert_any_call(
        "03921f8d-b4de-412e-a733-f8eade4c6268", "112233"
    )


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
        subnet_uuid="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        prefix="1.0.0.0/24",
        namespace_name="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
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

    driver.nb = nautobot_client
    driver.undersync = undersync_client

    driver.create_subnet_postcommit(context)

    nautobot_client.subnet_create.assert_called_once_with(
        subnet_uuid="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        prefix="1.0.0.0/24",
        namespace_name="Global",
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

    driver.nb = nautobot_client
    driver.undersync = undersync_client

    driver.delete_subnet_postcommit(context)

    nautobot_client.subnet_delete.assert_called_once()
