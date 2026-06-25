import logging

import ironic.objects
from oslo_utils import uuidutils

from ironic_understack.inspect_hook_update_baremetal_ports import (
    InspectHookUpdateBaremetalPorts,
)
from ironic_understack.inspect_hook_update_baremetal_ports import _is_our_trait
from ironic_understack.inspect_hook_update_baremetal_ports import (
    _network_group_trait_name,
)
from ironic_understack.inspect_hook_update_baremetal_ports import _trait_name

# load some metaprgramming normally taken care of during Ironic initialization:
ironic.objects.register_all()

_INVENTORY = {}
_PLUGIN_DATA = {
    "all_interfaces": {
        "ex1": {
            "name": "ex1",
            "mac_address": "11:11:11:11:11:11",
        },
        "ex2": {
            "name": "ex2",
            "mac_address": "22:22:22:22:22:22",
        },
        "ex3": {
            "name": "ex3",
            "mac_address": "33:33:33:33:33:33",
        },
        "ex4": {
            "name": "ex4",
            "mac_address": "44:44:44:44:44:44",
        },
    },
    "parsed_lldp": {
        "ex1": {
            "switch_chassis_id": "88:5a:92:ec:54:59",
            "switch_port_id": "Ethernet1/18",
            "switch_system_name": "f20-3-1.iad3",
        },
        "ex2": {
            "switch_chassis_id": "88:5a:92:ec:54:59",
            "switch_port_id": "Ethernet1/18",
            "switch_system_name": "f20-3-2.iad3",
        },
        "ex3": {
            "switch_chassis_id": "88:5a:92:ec:54:59",
            "switch_port_id": "Ethernet1/18",
            "switch_system_name": "f20-3-1f.iad3",
        },
        "ex4": {
            "switch_chassis_id": "88:5a:92:ec:54:59",
            "switch_port_id": "Ethernet1/18",
            "switch_system_name": "f20-3-2f.iad3",
        },
    },
}

MAPPING = {
    "1": "network",
    "2": "network",
    "1f": "storage",
    "2f": "storage",
    "-1d": "bmc",
}


def test_with_valid_network_port(mocker, caplog):
    caplog.set_level(logging.DEBUG)

    node_uuid = uuidutils.generate_uuid()
    mock_traits = mocker.Mock()
    mock_context = mocker.Mock()
    mock_node = mocker.Mock(id=1234, traits=mock_traits)
    mock_task = mocker.Mock(node=mock_node, context=mock_context)
    mock_port = mocker.Mock(
        uuid=uuidutils.generate_uuid(),
        node_id=node_uuid,
        address="11:11:11:11:11:11",
        local_link_connection={},
        physical_network="original_value",
        category=None,
        pxe_enabled=False,
    )

    mocker.patch(
        "ironic_understack.inspect_hook_update_baremetal_ports.ironic_ports_for_node",
        return_value=[mock_port],
    )
    mocker.patch(
        "ironic_understack.inspect_hook_update_baremetal_ports.CONF.ironic_understack.switch_name_vlan_group_mapping",
        MAPPING,
    )
    mocker.patch(
        "ironic_understack.inspect_hook_update_baremetal_ports.objects.TraitList.create"
    )
    mock_traits.get_trait_names.return_value = ["CUSTOM_BMC_SWITCH", "bar"]

    InspectHookUpdateBaremetalPorts().__call__(mock_task, _INVENTORY, _PLUGIN_DATA)

    assert mock_port.local_link_connection == {
        "port_id": "Ethernet1/18",
        "switch_id": "88:5a:92:ec:54:59",
        "switch_info": "f20-3-1.iad3.rackspace.net",
    }
    assert mock_port.physical_network == "f20-3-network"
    assert mock_port.category == "network"
    assert mock_port.pxe_enabled is True
    mock_port.save.assert_called()


def test_with_valid_storage_port(mocker, caplog):
    caplog.set_level(logging.DEBUG)

    node_uuid = uuidutils.generate_uuid()
    mock_traits = mocker.Mock()
    mock_context = mocker.Mock()
    mock_node = mocker.Mock(id=1234, traits=mock_traits)
    mock_task = mocker.Mock(node=mock_node, context=mock_context)
    mock_port = mocker.Mock(
        uuid=uuidutils.generate_uuid(),
        node_id=node_uuid,
        address="33:33:33:33:33:33",
        local_link_connection={},
        physical_network="original_value",
        category=None,
        pxe_enabled=True,
    )

    mocker.patch(
        "ironic_understack.inspect_hook_update_baremetal_ports.ironic_ports_for_node",
        return_value=[mock_port],
    )
    mocker.patch(
        "ironic_understack.inspect_hook_update_baremetal_ports.CONF.ironic_understack.switch_name_vlan_group_mapping",
        MAPPING,
    )
    mocker.patch(
        "ironic_understack.inspect_hook_update_baremetal_ports.objects.TraitList.create"
    )
    mock_traits.get_trait_names.return_value = ["CUSTOM_BMC_SWITCH", "bar"]

    InspectHookUpdateBaremetalPorts().__call__(mock_task, _INVENTORY, _PLUGIN_DATA)

    assert mock_port.local_link_connection == {
        "port_id": "Ethernet1/18",
        "switch_id": "88:5a:92:ec:54:59",
        "switch_info": "f20-3-1f.iad3.rackspace.net",
    }
    assert mock_port.physical_network is None
    assert mock_port.category == "storage"
    assert mock_port.pxe_enabled is False
    mock_port.save.assert_called()


def test_secondary_network_port_has_pxe_disabled(mocker, caplog):
    caplog.set_level(logging.DEBUG)

    node_uuid = uuidutils.generate_uuid()
    mock_traits = mocker.Mock()
    mock_context = mocker.Mock()
    mock_node = mocker.Mock(id=1234, traits=mock_traits)
    mock_task = mocker.Mock(node=mock_node, context=mock_context)
    mock_port = mocker.Mock(
        uuid=uuidutils.generate_uuid(),
        node_id=node_uuid,
        address="22:22:22:22:22:22",
        local_link_connection={},
        physical_network="original_value",
        category=None,
        pxe_enabled=True,
    )

    mocker.patch(
        "ironic_understack.inspect_hook_update_baremetal_ports.ironic_ports_for_node",
        return_value=[mock_port],
    )
    mocker.patch(
        "ironic_understack.inspect_hook_update_baremetal_ports.CONF.ironic_understack.switch_name_vlan_group_mapping",
        MAPPING,
    )
    mocker.patch(
        "ironic_understack.inspect_hook_update_baremetal_ports.objects.TraitList.create"
    )
    mock_traits.get_trait_names.return_value = ["CUSTOM_BMC_SWITCH", "bar"]

    InspectHookUpdateBaremetalPorts().__call__(mock_task, _INVENTORY, _PLUGIN_DATA)

    assert mock_port.local_link_connection == {
        "port_id": "Ethernet1/18",
        "switch_id": "88:5a:92:ec:54:59",
        "switch_info": "f20-3-2.iad3.rackspace.net",
    }
    assert mock_port.physical_network == "f20-3-network"
    assert mock_port.category == "network"
    assert mock_port.pxe_enabled is False
    mock_port.save.assert_called()


def test_node_traits_updated(mocker, caplog):
    caplog.set_level(logging.DEBUG)

    mock_traits = mocker.Mock()
    mock_context = mocker.Mock()
    mock_node = mocker.Mock(id=1234, traits=mock_traits)
    mock_task = mocker.Mock(node=mock_node, context=mock_context)

    mocker.patch(
        "ironic_understack.inspect_hook_update_baremetal_ports.ironic_ports_for_node",
        return_value=[],
    )
    mocker.patch(
        "ironic_understack.inspect_hook_update_baremetal_ports.CONF.ironic_understack.switch_name_vlan_group_mapping",
        MAPPING,
    )
    trait_create = mocker.patch(
        "ironic_understack.inspect_hook_update_baremetal_ports.objects.TraitList.create"
    )

    mock_traits.get_trait_names.return_value = ["CUSTOM_BMC_SWITCH", "bar"]

    InspectHookUpdateBaremetalPorts().__call__(mock_task, _INVENTORY, _PLUGIN_DATA)

    mock_node.save.assert_called_once()
    trait_create.assert_called_once_with(
        mock_context,
        1234,
        {
            "CUSTOM_STORAGE_SWITCH",
            "CUSTOM_NETWORK_SWITCH",
            "CUSTOM_NETGROUP_F20_3_NETWORK",
            "bar",
        },
    )


class TestTraitNames:
    def test_trait_name_network(self):
        assert _trait_name("f20-3-network") == "CUSTOM_NETWORK_SWITCH"

    def test_trait_name_storage(self):
        assert _trait_name("f20-3-storage") == "CUSTOM_STORAGE_SWITCH"

    def test_network_group_trait_simple(self):
        assert _network_group_trait_name("a1-1-network") == (
            "CUSTOM_NETGROUP_A1_1_NETWORK"
        )

    def test_network_group_trait_with_datacenter_prefix(self):
        assert _network_group_trait_name("f20-3-network") == (
            "CUSTOM_NETGROUP_F20_3_NETWORK"
        )

    def test_network_group_trait_cross_rack(self):
        """Cross-rack VLAN groups use slash separator."""
        assert _network_group_trait_name("a11-12/a11-13-network") == (
            "CUSTOM_NETGROUP_A11_12_A11_13_NETWORK"
        )

    def test_is_our_trait_switch_pattern(self):
        assert _is_our_trait("CUSTOM_NETWORK_SWITCH") is True
        assert _is_our_trait("CUSTOM_STORAGE_SWITCH") is True
        assert _is_our_trait("CUSTOM_BMC_SWITCH") is True

    def test_is_our_trait_netgroup_pattern(self):
        assert _is_our_trait("CUSTOM_NETGROUP_A1_1_NETWORK") is True
        assert _is_our_trait("CUSTOM_NETGROUP_F20_3_NETWORK") is True
        assert _is_our_trait("CUSTOM_NETGROUP_A11_12_A11_13_NETWORK") is True

    def test_is_our_trait_unrelated(self):
        """Traits we don't manage should not match."""
        assert _is_our_trait("CUSTOM_HW_SOMETHING") is False
        assert _is_our_trait("bar") is False
        assert _is_our_trait("CUSTOM_NETGROUP") is False


class TestNetgroupTraitIncludedInNodeTraits:
    """Verify that network group traits are added alongside switch traits."""

    def test_traits_include_netgroup(self, mocker, caplog):
        import logging

        caplog.set_level(logging.DEBUG)

        mock_traits = mocker.Mock()
        mock_context = mocker.Mock()
        mock_node = mocker.Mock(id=5678, traits=mock_traits)
        mock_task = mocker.Mock(node=mock_node, context=mock_context)

        mocker.patch(
            "ironic_understack.inspect_hook_update_baremetal_ports."
            "ironic_ports_for_node",
            return_value=[],
        )
        mocker.patch(
            "ironic_understack.inspect_hook_update_baremetal_ports."
            "CONF.ironic_understack.switch_name_vlan_group_mapping",
            MAPPING,
        )
        trait_create = mocker.patch(
            "ironic_understack.inspect_hook_update_baremetal_ports."
            "objects.TraitList.create"
        )

        # Existing traits include one we manage and one we don't
        mock_traits.get_trait_names.return_value = [
            "CUSTOM_NETWORK_SWITCH",
            "CUSTOM_UNRELATED_THING",
        ]

        InspectHookUpdateBaremetalPorts().__call__(mock_task, _INVENTORY, _PLUGIN_DATA)

        mock_node.save.assert_called_once()
        created_traits = trait_create.call_args[0][2]

        # Should include both switch-type traits and netgroup trait
        assert "CUSTOM_NETWORK_SWITCH" in created_traits
        assert "CUSTOM_STORAGE_SWITCH" in created_traits
        assert "CUSTOM_NETGROUP_F20_3_NETWORK" in created_traits
        # Unrelated trait should be preserved
        assert "CUSTOM_UNRELATED_THING" in created_traits
        # Old managed traits from different groups should be removed
        # (none in this case, but let's verify no spurious ones)
        for trait in created_traits:
            if trait.startswith("CUSTOM_NETGROUP_"):
                assert trait == "CUSTOM_NETGROUP_F20_3_NETWORK"
