from dataclasses import dataclass
from unittest.mock import ANY

import pytest

from neutron_understack import utils
from neutron_understack.nautobot import VlanPayload


class TestUpdatePortPostCommit:
    def test_with_simple_port(self, understack_driver, port_context):
        understack_driver.update_port_postcommit(port_context)

        understack_driver.undersync.sync_devices.assert_called_once()


@pytest.mark.usefixtures("ironic_baremetal_port_physical_network")
class TestBindPort:
    def test_with_no_trunk(
        self,
        mocker,
        port_context,
        understack_driver,
        understack_trunk_driver,
        vlan_network_segment,
    ):
        mocker.patch(
            "neutron_understack.utils.fetch_connected_interface_uuid",
            return_value="FAKE ID",
        )
        mocker.patch.object(
            port_context, "allocate_dynamic_segment", return_value=vlan_network_segment
        )
        mocker.patch.object(understack_driver.nb, "set_port_vlan_associations")

        understack_driver.bind_port(port_context)
        understack_driver.trunk_driver = understack_trunk_driver

        port_context.allocate_dynamic_segment.assert_called_once()
        utils.fetch_connected_interface_uuid.assert_called_once()

        understack_driver.nb.set_port_vlan_associations.assert_called_once_with(
            interface_uuid="FAKE ID",
            native_vlan_id=1800,
            allowed_vlans_ids={1800},
            vlan_group_name="physnet",
        )

    @pytest.mark.parametrize("port_dict", [{"trunk": True}], indirect=True)
    def test_with_trunk_details(
        self, mocker, understack_driver, port_context, understack_trunk_driver
    ):
        mocker.patch(
            "neutron_understack.utils.fetch_subport_network_id", return_value="112233"
        )

        understack_driver.trunk_driver = understack_trunk_driver
        mocker.patch.object(understack_driver.trunk_driver, "configure_trunk")
        understack_driver.bind_port(port_context)
        understack_driver.trunk_driver.configure_trunk.assert_called_once()


class TestCreateSubnetPostCommit:
    def test_create_private(self, understack_driver, subnet_context, subnet):
        understack_driver.create_subnet_postcommit(subnet_context)

        understack_driver.nb.subnet_create.assert_called_once_with(
            subnet_uuid=subnet.id,
            prefix=subnet.cidr,
            namespace_name=subnet.network_id,
            tenant_uuid=ANY,
        )

    @pytest.mark.parametrize("subnet", [{"external": True}], indirect=True)
    def test_create_public(self, understack_driver, subnet_context, subnet):
        understack_driver.create_subnet_postcommit(subnet_context)

        understack_driver.nb.subnet_create.assert_called_once_with(
            subnet_uuid=subnet.id,
            prefix=subnet.cidr,
            namespace_name="Global",
            tenant_uuid=ANY,
        )
        understack_driver.nb.associate_subnet_with_network.assert_called_once_with(
            network_uuid=subnet.network_id,
            subnet_uuid=subnet.id,
        )
        understack_driver.nb.set_svi_role_on_network.assert_called_once_with(
            network_uuid=subnet.network_id,
            role="svi_vxlan_anycast_gateway",
        )


class TestDeleteSubnetPostCommit:
    @pytest.mark.parametrize("subnet", [{"external": True}], indirect=True)
    def test_delete_public(self, understack_driver, subnet_context):
        understack_driver.delete_subnet_postcommit(subnet_context)

        understack_driver.nb.subnet_delete.assert_called_once()


class TestNetworkSegmentEventCallbacks:
    @pytest.mark.parametrize(
        "vlan_network_segment", [{"physical_network": "f20-2-network"}], indirect=True
    )
    def test__create_vlan_valid_segment(
        self, mocker, vlan_network_segment, understack_driver
    ):
        mocker.patch(
            "neutron_understack.utils.is_valid_vlan_network_segment", return_value=True
        )

        mock_create = mocker.patch.object(
            understack_driver.nb, "create_vlan_and_associate_vlan_to_ucvni"
        )

        understack_driver._create_vlan(vlan_network_segment)

        mock_create.assert_called_once()
        vlan_payload: VlanPayload = mock_create.call_args[0][0]

        assert vlan_payload.vid == 1800
        assert vlan_payload.vlan_group_name == "f20-2-network"

    def test__create_vlan_invalid_segment(
        self, mocker, vlan_network_segment, understack_driver
    ):
        mocker.patch(
            "neutron_understack.utils.is_valid_vlan_network_segment", return_value=False
        )
        mock_create = mocker.patch.object(
            understack_driver.nb, "create_vlan_and_associate_vlan_to_ucvni"
        )

        understack_driver._create_vlan(vlan_network_segment)

        mock_create.assert_not_called()

    @pytest.mark.parametrize(
        "vlan_network_segment",
        [{"physical_network": "f20-2-network", "segmentation_id": 100}],
        indirect=True,
    )
    def test__delete_vlan(self, mocker, vlan_network_segment, understack_driver):
        mock_delete = mocker.patch.object(understack_driver.nb, "delete_vlan")
        understack_driver._delete_vlan(vlan_network_segment)
        mock_delete.assert_called_once_with(vlan_id=vlan_network_segment.get("id"))


class TestCreateNetworkPostCommit:
    @pytest.mark.usefixtures("ml2_understack_conf")
    def test_vxlan_network(
        self,
        mocker,
        understack_driver,
        network_context,
        network_id,
        ucvni_group_id,
        project_id,
    ):
        mocker.patch.object(understack_driver, "_create_nautobot_namespace")

        @dataclass
        class FakeContext:
            current = {
                "id": "3b5f0bb1-cd53-4c71-b129-1fe7550dfdf4",
                "name": "humpback",
                "tenant_id": "f9b40d4a39c4403ab5567da17e71906a",
                "admin_state_up": True,
                "mtu": 9000,
                "status": "ACTIVE",
                "subnets": [],
                "standard_attr_id": 3926,
                "shared": False,
                "project_id": "f9b40d4a39c4403ab5567da17e71906a",
                "router:external": False,
                "provider:network_type": "vxlan",
                "provider:physical_network": None,
                "provider:segmentation_id": 200025,
                "is_default": False,
                "availability_zone_hints": [],
                "availability_zones": [],
                "ipv4_address_scope": None,
                "ipv6_address_scope": None,
                "vlan_transparent": None,
                "description": "",
                "l2_adjacency": True,
                "tags": [],
                "created_at": "2025-03-14T07:06:52Z",
                "updated_at": "2025-03-14T07:06:52Z",
                "revision_number": 1,
            }
            network_segments = [
                {
                    "id": "9e56eb8d-f9ec-47d2-ac80-3fde76087c38",
                    "network_type": "vxlan",
                    "physical_network": None,
                    "segmentation_id": 200025,
                    "network_id": "3b5f0bb1-cd53-4c71-b129-1fe7550dfdf4",
                }
            ]

        understack_driver.create_network_postcommit(FakeContext())

        understack_driver.nb.ucvni_create.assert_called_once_with(
            network_id="3b5f0bb1-cd53-4c71-b129-1fe7550dfdf4",
            project_id="f9b40d4a39c4403ab5567da17e71906a",
            ucvni_group=str(ucvni_group_id),
            segmentation_id=200025,
            network_name="humpback",
        )
        understack_driver._create_nautobot_namespace.assert_called_once_with(
            "3b5f0bb1-cd53-4c71-b129-1fe7550dfdf4",
            network_context.current["router:external"],
        )
