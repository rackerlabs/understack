import logging

import ironic.objects
from oslo_utils import uuidutils

from ironic_understack.inspect_hook_update_baremetal_ports import (
    InspectHookUpdateBaremetalPorts,
)

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
        mock_context, 1234, {"CUSTOM_STORAGE_SWITCH", "CUSTOM_NETWORK_SWITCH", "bar"}
    )
