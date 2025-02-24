from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from neutron_understack.nautobot import Nautobot
from neutron_understack.neutron_understack_mech import UnderstackDriver
from neutron_understack.trunk import SubportSegmentationIDError
from neutron_understack.trunk import UnderStackTrunkDriver


@pytest.fixture
def subport() -> MagicMock:
    return MagicMock(port_id="portUUID", segmentation_id=555)


@pytest.fixture
def trunk(subport) -> MagicMock:
    return MagicMock(sub_ports=[subport])


@pytest.fixture
def payload_metadata(subport) -> dict:
    return {"subports": [subport]}


@pytest.fixture
def payload(payload_metadata, trunk) -> MagicMock:
    return MagicMock(metadata=payload_metadata, states=[trunk])


@pytest.fixture
def nautobot_client() -> Nautobot:
    return MagicMock(spec_set=Nautobot)


driver = UnderstackDriver()
driver.nb = Nautobot("", "")
trunk_driver = UnderStackTrunkDriver.create(driver)


@patch("neutron_understack.utils.fetch_subport_network_id", return_value="112233")
def test_subports_added_when_ucvni_tenan_vlan_id_is_not_set_yet(
    nautobot_client, payload
):
    trunk_driver.nb = nautobot_client
    attrs = {"fetch_ucvni_tenant_vlan_id.return_value": None}
    nautobot_client.configure_mock(**attrs)
    trunk_driver.subports_added("", "", "", payload)

    nautobot_client.add_tenant_vlan_tag_to_ucvni.assert_called_once_with(
        network_uuid="112233", vlan_tag=555
    )


@patch("neutron_understack.utils.fetch_subport_network_id", return_value="223344")
def test_subports_added_when_segmentation_id_is_different_to_tenant_vlan_id(
    nautobot_client, payload
):
    trunk_driver.nb = nautobot_client
    attrs = {"fetch_ucvni_tenant_vlan_id.return_value": 123}
    nautobot_client.configure_mock(**attrs)
    with pytest.raises(SubportSegmentationIDError):
        trunk_driver.subports_added("", "", "", payload)


@patch("neutron_understack.utils.fetch_subport_network_id", return_value="112233")
def test_trunk_created_when_ucvni_tenan_vlan_id_is_not_set_yet(
    nautobot_client, payload
):
    trunk_driver.nb = nautobot_client
    attrs = {"fetch_ucvni_tenant_vlan_id.return_value": None}
    nautobot_client.configure_mock(**attrs)
    trunk_driver.trunk_created("", "", "", payload)

    nautobot_client.add_tenant_vlan_tag_to_ucvni.assert_called_once_with(
        network_uuid="112233", vlan_tag=555
    )


@patch("neutron_understack.utils.fetch_subport_network_id", return_value="223344")
def test_trunk_created_when_segmentation_id_is_different_to_tenant_vlan_id(
    nautobot_client, payload
):
    trunk_driver.nb = nautobot_client
    attrs = {"fetch_ucvni_tenant_vlan_id.return_value": 123}
    nautobot_client.configure_mock(**attrs)
    with pytest.raises(SubportSegmentationIDError):
        trunk_driver.trunk_created("", "", "", payload)
