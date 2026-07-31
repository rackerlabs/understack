from unittest.mock import MagicMock

import pytest
from neutron_lib.api.definitions import portbindings
from neutron_lib.services.trunk import constants as trunk_consts

from neutron_understack.undersync_trunk import PhysicalNetworkNotFoundError


@pytest.fixture
def bound_parent_port():
    binding = MagicMock()
    binding.vif_type = portbindings.VIF_TYPE_OTHER
    binding.vnic_type = portbindings.VNIC_BAREMETAL
    binding.profile = {"physical_network": "physnet-a"}

    binding_level = MagicMock()
    binding_level.driver = "undersync"

    port = MagicMock()
    port.id = "parent-port-1"
    port.bindings = [binding]
    port.binding_levels = [binding_level]
    return port


@pytest.fixture
def bound_parent_port_without_physnet(bound_parent_port):
    bound_parent_port.bindings[0].profile = {"local_link_information": []}
    return bound_parent_port


@pytest.fixture
def unbound_parent_port(bound_parent_port):
    bound_parent_port.bindings[0].vif_type = portbindings.VIF_TYPE_UNBOUND
    return bound_parent_port


@pytest.fixture
def parent_port_bound_by_other_driver(bound_parent_port):
    bound_parent_port.binding_levels[0].driver = "understack"
    return bound_parent_port


class TestSubportsAdded:
    def test_calls_sync_parent_port_physical_network(
        self, mocker, undersync_trunk_driver, trunk_payload, trunk
    ):
        sync = mocker.patch.object(
            undersync_trunk_driver, "_sync_parent_port_physical_network"
        )
        update = mocker.patch.object(trunk, "update")

        undersync_trunk_driver.subports_added("", "", "", trunk_payload)

        sync.assert_called_once_with(trunk)
        update.assert_called_once_with(status=trunk_consts.TRUNK_ACTIVE_STATUS)


class TestSubportsDeleted:
    def test_calls_sync_parent_port_physical_network(
        self, mocker, undersync_trunk_driver, trunk_payload, trunk
    ):
        sync = mocker.patch.object(
            undersync_trunk_driver, "_sync_parent_port_physical_network"
        )

        undersync_trunk_driver.subports_deleted("", "", "", trunk_payload)

        sync.assert_called_once_with(trunk)


class TestSyncParentPortPhysicalNetwork:
    def test_syncs_when_parent_port_bound_with_physical_network(
        self, mocker, undersync_trunk_driver, trunk, bound_parent_port
    ):
        mocker.patch(
            "neutron_understack.utils.fetch_port_object",
            return_value=bound_parent_port,
        )

        undersync_trunk_driver._sync_parent_port_physical_network(trunk)

        undersync_trunk_driver.undersync.sync.assert_called_once_with("physnet-a")

    def test_skips_when_parent_port_is_unbound(
        self, mocker, undersync_trunk_driver, trunk, unbound_parent_port
    ):
        mocker.patch(
            "neutron_understack.utils.fetch_port_object",
            return_value=unbound_parent_port,
        )

        undersync_trunk_driver._sync_parent_port_physical_network(trunk)

        undersync_trunk_driver.undersync.sync.assert_not_called()

    def test_raises_when_physical_network_missing(
        self, mocker, undersync_trunk_driver, trunk, bound_parent_port_without_physnet
    ):
        mocker.patch(
            "neutron_understack.utils.fetch_port_object",
            return_value=bound_parent_port_without_physnet,
        )

        with pytest.raises(PhysicalNetworkNotFoundError):
            undersync_trunk_driver._sync_parent_port_physical_network(trunk)

        undersync_trunk_driver.undersync.sync.assert_not_called()

    def test_skips_when_parent_port_not_bound_by_undersync(
        self, mocker, undersync_trunk_driver, trunk, parent_port_bound_by_other_driver
    ):
        mocker.patch(
            "neutron_understack.utils.fetch_port_object",
            return_value=parent_port_bound_by_other_driver,
        )

        undersync_trunk_driver._sync_parent_port_physical_network(trunk)

        undersync_trunk_driver.undersync.sync.assert_not_called()
