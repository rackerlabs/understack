import logging

import ironic.objects
from oslo_utils import uuidutils

from ironic_understack.update_baremetal_port import UpdateBaremetalPortsHook

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


def test_with_valid_data(mocker, caplog):
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
    )

    mocker.patch(
        "ironic_understack.update_baremetal_port.ironic_ports_for_node",
        return_value=[mock_port],
    )
    mocker.patch(
        "ironic_understack.update_baremetal_port.CONF.ironic_understack.switch_name_vlan_group_mapping",
        MAPPING,
    )
    mocker.patch("ironic_understack.update_baremetal_port.objects.TraitList.create")

    mock_traits.get_trait_names.return_value = ["CUSTOM_BMC_SWITCH", "bar"]

    UpdateBaremetalPortsHook().__call__(mock_task, _INVENTORY, _PLUGIN_DATA)

    assert mock_port.local_link_connection == {
        "port_id": "Ethernet1/18",
        "switch_id": "88:5a:92:ec:54:59",
        "switch_info": "f20-3-1.iad3.rackspace.net",
    }
    assert mock_port.physical_network == "f20-3-network"
    mock_port.save.assert_called()
    mock_node.save.assert_called_once()
