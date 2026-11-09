from unittest import mock

import pytest
from neutron.plugins.ml2.drivers.ovn.mech_driver import mech_driver
from oslo_config import cfg

from neutron_understack import fabric_vlan


def test_ovn_mech_driver_keeps_the_alias(mocker, oslo_config):
    mocker.patch.object(fabric_vlan.n_extensions, "append_api_extensions_path")
    mocker.patch.object(fabric_vlan.registry, "subscribe")
    mocker.patch.object(fabric_vlan.n_context, "get_admin_context")
    mocker.patch.object(fabric_vlan, "find_fabric_vlan_range")
    mocker.patch.object(
        fabric_vlan.ovn_extensions,
        "ML2_SUPPORTED_API_EXTENSIONS",
        list(fabric_vlan.ovn_extensions.ML2_SUPPORTED_API_EXTENSIONS),
    )
    fabric_vlan.UnderstackFabricVlanExtensionDriver().initialize()

    ovn_driver = mech_driver.OVNMechanismDriver.__new__(mech_driver.OVNMechanismDriver)
    alias = fabric_vlan.apidef.ALIAS
    assert ovn_driver.supported_extensions({alias}) == {alias}


class TestFabricVlanRangeCache:
    @pytest.fixture
    def range_obj(self, mocker):
        return mocker.patch.object(fabric_vlan, "NetworkSegmentRange")

    @pytest.fixture
    def context(self, mocker):
        context = mocker.Mock()
        context.elevated.return_value = context
        return context

    @pytest.fixture
    def driver(self, mocker, oslo_config):
        mocker.patch.object(fabric_vlan.n_extensions, "append_api_extensions_path")
        mocker.patch.object(fabric_vlan.registry, "subscribe")
        mocker.patch.object(fabric_vlan.n_context, "get_admin_context")
        return fabric_vlan.UnderstackFabricVlanExtensionDriver()

    def test_physnet_defaults_to_understack_fabric_vlan(self, oslo_config):
        assert (
            cfg.CONF.ml2_understack.fabric_vlan_physical_network
            == "understack_fabric_vlan"
        )

    def test_startup_looks_up_the_physnet_once_and_caches_the_id(
        self, driver, range_obj, context
    ):
        range_obj.get_objects.return_value = [fabric_range("range-1")]
        driver.initialize()
        range_obj.get_objects.assert_called_once_with(
            mock.ANY, network_type="vlan", physical_network="understack_fabric_vlan"
        )

        range_obj.get_object.return_value = fabric_range("range-1")
        for _ in range(3):
            assert driver._fabric_vlan_range(context).id == "range-1"

        range_obj.get_objects.assert_called_once()
        range_obj.get_object.assert_called_with(context, id="range-1")

    def test_range_missing_at_startup_is_looked_up_on_first_use(
        self, driver, range_obj, context
    ):
        range_obj.get_objects.return_value = []
        driver.initialize()
        assert driver._range_id is None

        range_obj.get_objects.return_value = [fabric_range("range-1")]
        assert driver._fabric_vlan_range(context).id == "range-1"
        assert driver._range_id == "range-1"

    def test_deleted_range_is_looked_up_again_by_physnet(
        self, driver, range_obj, context
    ):
        range_obj.get_objects.return_value = [fabric_range("range-1")]
        driver.initialize()

        range_obj.get_object.return_value = None
        range_obj.get_objects.return_value = [fabric_range("range-2")]
        assert driver._fabric_vlan_range(context).id == "range-2"
        assert driver._range_id == "range-2"

    def test_no_range_is_an_error_at_use(self, driver, range_obj, context):
        range_obj.get_objects.return_value = []
        driver.initialize()

        with pytest.raises(fabric_vlan.FabricVlanRangeNotFound):
            driver._fabric_vlan_range(context)


def fabric_range(range_id):
    return mock.Mock(id=range_id)
