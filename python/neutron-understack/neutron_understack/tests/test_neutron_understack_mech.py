from dataclasses import dataclass

import pytest
from neutron_lib.api.definitions import portbindings
from neutron_lib.plugins.ml2 import api
from oslo_config import cfg

from neutron_understack.neutron_understack_mech import UnderstackDriver


class TestUpdatePortPostCommit:
    def test_with_simple_port(self, understack_driver, port_context):
        understack_driver.update_port_postcommit(port_context)

        understack_driver.undersync.sync_devices.assert_called_once()

    def test_skips_non_baremetal_port(self, understack_driver, port_context):
        port_context.current[portbindings.VNIC_TYPE] = portbindings.VNIC_NORMAL

        understack_driver.update_port_postcommit(port_context)

        understack_driver.undersync.sync_devices.assert_not_called()


class TestDeletePortPostCommit:
    def test_skips_non_baremetal_port(self, understack_driver, port_context):
        port_context.current[portbindings.VNIC_TYPE] = portbindings.VNIC_NORMAL

        understack_driver.delete_port_postcommit(port_context)

        understack_driver.undersync.sync_devices.assert_not_called()


@pytest.mark.usefixtures("_ironic_baremetal_port_physical_network")
class TestBindPort:
    def test_does_not_bind_vlan_only_segments(
        self,
        mocker,
        port_context,
        understack_driver,
        vlan_network_segment,
    ):
        """At level 1 understack receives only the VLAN segment and should do nothing.

        undersync is responsible for that binding.
        """
        port_context._prepare_to_bind([vlan_network_segment])
        mocker.patch.object(port_context, "continue_binding")

        understack_driver.bind_port(port_context)

        port_context.continue_binding.assert_not_called()

    def test_uses_existing_vlan_segment(
        self,
        mocker,
        port_context,
        understack_driver,
        vlan_network_segment,
    ):
        """When a VLAN segment already exists for the physnet, reuse it.

        It should not allocate a new dynamic segment.
        """
        mocker.patch.object(port_context, "allocate_dynamic_segment")
        mocker.patch.object(port_context, "continue_binding")
        mocker.patch(
            "neutron_understack.neutron_understack_mech.utils.vlan_segment_for_physnet",
            return_value=vlan_network_segment,
        )
        port_context._prepare_to_bind(port_context.network.network_segments)

        understack_driver.bind_port(port_context)

        port_context.allocate_dynamic_segment.assert_not_called()
        vxlan_segment = next(
            s
            for s in port_context.network.network_segments
            if s[api.NETWORK_TYPE] == "vxlan"
        )
        port_context.continue_binding.assert_called_once_with(
            segment_id=vxlan_segment[api.ID],
            next_segments_to_bind=[vlan_network_segment],
        )

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
        mocker.patch.object(port_context, "continue_binding")
        port_context._prepare_to_bind(port_context.network.network_segments)

        understack_driver.bind_port(port_context)
        understack_driver.trunk_driver = understack_trunk_driver

        port_context.allocate_dynamic_segment.assert_called_once()
        vxlan_segment = next(
            s
            for s in port_context.network.network_segments
            if s[api.NETWORK_TYPE] == "vxlan"
        )
        port_context.continue_binding.assert_called_once_with(
            segment_id=vxlan_segment[api.ID],
            next_segments_to_bind=[vlan_network_segment],
        )

    def test_refuses_unsupported_vnic_type(
        self, mocker, port_context, understack_driver
    ):
        port_context.current[portbindings.VNIC_TYPE] = portbindings.VNIC_DIRECT
        mocker.patch.object(port_context, "continue_binding")
        port_context._prepare_to_bind(port_context.network.network_segments)

        understack_driver.bind_port(port_context)

        port_context.continue_binding.assert_not_called()

    @pytest.mark.usefixtures("_ironic_baremetal_port_physical_network")
    def test_does_not_bind_when_physical_network_not_found(
        self, mocker, port_context, understack_driver
    ):
        understack_driver.ironic_client.baremetal_port_physical_network.return_value = (
            None
        )
        mocker.patch.object(port_context, "continue_binding")
        port_context._prepare_to_bind(port_context.network.network_segments)

        understack_driver.bind_port(port_context)

        port_context.continue_binding.assert_not_called()

    @pytest.mark.parametrize("port_dict", [{"trunk": True}], indirect=True)
    def test_with_trunk_details(
        self, mocker, understack_driver, port_context, understack_trunk_driver
    ):
        mocker.patch(
            "neutron_understack.utils.fetch_subport_network_id", return_value="112233"
        )
        mocker.patch.object(port_context, "continue_binding")
        port_context._prepare_to_bind(port_context.network.network_segments)

        understack_driver.trunk_driver = understack_trunk_driver
        mocker.patch.object(understack_driver.trunk_driver, "configure_trunk")
        understack_driver.bind_port(port_context)
        understack_driver.trunk_driver.configure_trunk.assert_called_once()
        port_context.continue_binding.assert_called_once()


class TestCreateNetworkPostCommit:
    @pytest.mark.usefixtures("_ml2_understack_conf")
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


class TestKeystoneAuthentication:
    def test_initialize_with_keystone_auth(self, mocker):
        """Test that driver initializes with Keystone authentication."""
        mock_auth = mocker.patch("keystoneauth1.loading.load_auth_from_conf_options")
        mock_session_class = mocker.patch(
            "neutron_understack.neutron_understack_mech.ks_session.Session"
        )
        mock_get_token = mocker.MagicMock(return_value="test_service_token")

        mock_session_instance = mocker.MagicMock()
        mock_session_instance.get_token = mock_get_token
        mock_session_class.return_value = mock_session_instance

        # Mock IronicClient to avoid config issues
        mocker.patch("neutron_understack.neutron_understack_mech.IronicClient")

        driver = UnderstackDriver()
        driver.initialize()

        mock_auth.assert_called_once_with(cfg.CONF, "keystone_authtoken")
        mock_session_class.assert_called_once()
        mock_get_token.assert_called_once()
        assert driver.undersync.session == mock_session_instance
