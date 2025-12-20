import logging

from oslo_utils import uuidutils

from ironic_understack.port_bios_name_hook import PortBiosNameHook

_INVENTORY = {
    "memory": {"physical_mb": 98304},
    "interfaces": [
        {"mac_address": "11:11:11:11:11:11", "name": "NIC.Integrated.1-1"},
        {"mac_address": "22:22:22:22:22:22", "name": "NIC.Integrated.1-2"},
    ],
}


def test_adding_bios_name(mocker, caplog):
    caplog.set_level(logging.DEBUG)

    node_uuid = uuidutils.generate_uuid()
    mock_context = mocker.Mock()
    mock_node = mocker.Mock(id=1234)
    mock_node.name = "Dell-CR1MB0"
    mock_task = mocker.Mock(node=mock_node, context=mock_context)
    mock_port = mocker.Mock(
        uuid=uuidutils.generate_uuid(),
        node_id=node_uuid,
        address="11:11:11:11:11:11",
        extra={},
        local_link_connection={},
        physical_network=None,
    )
    mock_port.name = "some-arbitrary-name"

    mocker.patch(
        "ironic_understack.port_bios_name_hook.ironic_ports_for_node",
        return_value=[mock_port],
    )

    PortBiosNameHook().__call__(mock_task, _INVENTORY, {})

    assert mock_port.extra == {"bios_name": "NIC.Integrated.1-1"}
    assert mock_port.name == "Dell-CR1MB0:NIC.Integrated.1-1"
    assert mock_port.pxe_enabled
    assert mock_port.physical_network == "enrol"
    assert mock_port.local_link_connection == {
        "port_id": "None",
        "switch_id": "00:00:00:00:00:00",
        "switch_info": "None",
    }
    mock_port.save.assert_called()


def test_retaining_physical_network(mocker, caplog):
    caplog.set_level(logging.DEBUG)

    node_uuid = uuidutils.generate_uuid()
    mock_context = mocker.Mock()
    mock_node = mocker.Mock(id=1234)
    mock_node.name = "Dell-CR1MB0"
    mock_task = mocker.Mock(node=mock_node, context=mock_context)
    mock_port = mocker.Mock(
        uuid=uuidutils.generate_uuid(),
        node_id=node_uuid,
        address="11:11:11:11:11:11",
        extra={},
        local_link_connection={
            "port_id": "Ethernet1/19",
            "switch_id": "00:00:00:00:00:00",
            "switch_info": "a1-2-3",
        },
        physical_network="previous_value",
    )
    mock_port.name = "some-arbitrary-name"

    mocker.patch(
        "ironic_understack.port_bios_name_hook.ironic_ports_for_node",
        return_value=[mock_port],
    )

    PortBiosNameHook().__call__(mock_task, _INVENTORY, {})

    assert mock_port.extra == {"bios_name": "NIC.Integrated.1-1"}
    assert mock_port.name == "Dell-CR1MB0:NIC.Integrated.1-1"
    assert mock_port.pxe_enabled
    assert mock_port.physical_network == "previous_value"
    assert mock_port.local_link_connection == {
        "port_id": "Ethernet1/19",
        "switch_id": "00:00:00:00:00:00",
        "switch_info": "a1-2-3",
    }
    mock_port.save.assert_called()


def test_removing_bios_name(mocker, caplog):
    caplog.set_level(logging.DEBUG)

    node_uuid = uuidutils.generate_uuid()
    mock_context = mocker.Mock()
    mock_node = mocker.Mock(id=1234)
    mock_node.name = "Dell-CR1MB0"
    mock_task = mocker.Mock(node=mock_node, context=mock_context)
    mock_port = mocker.Mock(
        uuid=uuidutils.generate_uuid(),
        node_id=node_uuid,
        address="33:33:33:33:33:33",
        extra={"bios_name": "old_name_no_longer_valid"},
    )
    mock_port.name = "original-name"

    mocker.patch(
        "ironic_understack.port_bios_name_hook.ironic_ports_for_node",
        return_value=[mock_port],
    )

    PortBiosNameHook().__call__(mock_task, _INVENTORY, {})

    assert mock_port.name == "original-name"
    assert "bios_name" not in mock_port.extra
    mock_port.save.assert_called()
