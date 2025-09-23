from dataclasses import dataclass

import pytest


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
        mocker.patch.object(
            port_context, "allocate_dynamic_segment", return_value=vlan_network_segment
        )

        understack_driver.bind_port(port_context)
        understack_driver.trunk_driver = understack_trunk_driver

        port_context.allocate_dynamic_segment.assert_called_once()

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
