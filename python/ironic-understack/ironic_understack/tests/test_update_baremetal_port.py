from ironic.objects import port as ironic_port
from oslo_utils import uuidutils

from ironic_understack.update_baremetal_port import UpdateBaremetalPortsHook

_INTERFACE_1 = {
    "name": "example1",
    "mac_address": "11:11:11:11:11:11",
    "ipv4_address": "1.1.1.1",
    "lldp": [
        (0, ""),
        (1, "04885a92ec5459"),
        (2, "0545746865726e6574312f3138"),
        (3, "0078"),
        (5, "6632302d332d32662e69616433"),
    ],
}

_PLUGIN_DATA = {"all_interfaces": {"example1": _INTERFACE_1}}

_INVENTORY = {"interfaces": [_INTERFACE_1]}


def test_with_valid_data(mocker):
    node_uuid = uuidutils.generate_uuid()
    mock_traits = mocker.Mock()
    mock_node = mocker.Mock(traits=mock_traits)
    mock_task = mocker.Mock(node=mock_node)
    mock_port = mocker.Mock(
        uuid=uuidutils.generate_uuid(),
        node_id=node_uuid,
        address="11:11:11:11:11:11",
        local_link_connection={},
        physical_network="original_value",
    )
    mocker.patch(
        "ironic_understack.update_baremetal_port.objects.port.Port.get_by_address",
        return_value=mock_port,
    )

    mock_traits.get_trait_names.return_value = ["CUSTOM_NETWORK_SWITCH", "bar"]

    UpdateBaremetalPortsHook().__call__(mock_task, _INVENTORY, _PLUGIN_DATA)

    assert mock_port.local_link_connection == {
        "port_id": "Ethernet1/18",
        "switch_id": "88:5a:92:ec:54:59",
        "switch_info": "f20-3-2f.iad3",
    }
    assert mock_port.physical_network == "f20-3-storage"
    mock_port.save.assert_called()

    mock_traits.get_trait_names.assert_called_once()
    mock_traits.destroy.assert_called_once_with("CUSTOM_NETWORK_SWITCH")
    mock_traits.create.assert_called_once_with("CUSTOM_STORAGE_SWITCH")
    mock_node.save.assert_called_once()
