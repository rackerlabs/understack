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


def _make_task(mocker):
    mock_node = mocker.Mock(id=1234, uuid=uuidutils.generate_uuid(), extra={})
    mock_node.name = "Dell-CR1MB0"
    return mocker.Mock(node=mock_node, context=mocker.Mock())


def _make_port(mocker, mac, **kwargs):
    defaults = {
        "uuid": uuidutils.generate_uuid(),
        "address": mac,
        "extra": {},
        "pxe_enabled": False,
        "physical_network": None,
        "local_link_connection": {},
    }
    defaults.update(kwargs)
    port = mocker.Mock(**defaults)
    port.name = kwargs.get("name", "some-arbitrary-name")
    return port


def test_pxe_fallback(mocker, caplog):
    """Enables one PXE ports."""
    caplog.set_level(logging.DEBUG)
    task = _make_task(mocker)

    port1 = _make_port(mocker, "11:11:11:11:11:11")
    port2 = _make_port(mocker, "22:22:22:22:22:22")

    mocker.patch(
        "ironic_understack.port_bios_name_hook.ironic_ports_for_node",
        return_value=[port1, port2],
    )

    PortBiosNameHook().__call__(task, _INVENTORY, {})

    assert port1.pxe_enabled is True
    assert port2.pxe_enabled is False


def test_enables_slot_ports_too(mocker, caplog):
    """Missing enrolled_pxe_ports enables one PXE port prefixes."""
    caplog.set_level(logging.DEBUG)
    task = _make_task(mocker)
    inventory = {
        "memory": {"physical_mb": 98304},
        "interfaces": [
            {"mac_address": "11:11:11:11:11:11", "name": "NIC.Slot.1-2"},
            {"mac_address": "22:22:22:22:22:22", "name": "NIC.Integrated.1-1"},
            {"mac_address": "33:33:33:33:33:33", "name": "eno1"},
        ],
    }

    port1 = _make_port(mocker, "11:11:11:11:11:11")
    port2 = _make_port(mocker, "22:22:22:22:22:22")
    port3 = _make_port(mocker, "33:33:33:33:33:33")

    mocker.patch(
        "ironic_understack.port_bios_name_hook.ironic_ports_for_node",
        return_value=[port1, port2, port3],
    )

    PortBiosNameHook().__call__(task, inventory, {})

    assert port1.pxe_enabled is True
    assert port2.pxe_enabled is False
    assert port3.pxe_enabled is False


def test_retaining_physical_network(mocker, caplog):
    """Existing physical_network and local_link_connection are preserved."""
    caplog.set_level(logging.DEBUG)
    task = _make_task(mocker)

    port = _make_port(
        mocker,
        "11:11:11:11:11:11",
        pxe_enabled=True,
        physical_network="previous_value",
        local_link_connection={
            "port_id": "Ethernet1/19",
            "switch_id": "00:00:00:00:00:00",
            "switch_info": "a1-2-3",
        },
    )

    mocker.patch(
        "ironic_understack.port_bios_name_hook.ironic_ports_for_node",
        return_value=[port],
    )

    PortBiosNameHook().__call__(task, _INVENTORY, {})

    assert port.physical_network == "previous_value"
    assert port.local_link_connection["port_id"] == "Ethernet1/19"


def test_preserves_pxe_on_post_enroll_ports(mocker, caplog):
    """Post-enroll inspection keeps the existing PXE decision."""
    caplog.set_level(logging.DEBUG)
    task = _make_task(mocker)

    port1 = _make_port(
        mocker,
        "11:11:11:11:11:11",
        pxe_enabled=True,
        physical_network="f20-1-network",
    )
    port2 = _make_port(
        mocker,
        "22:22:22:22:22:22",
        pxe_enabled=False,
        physical_network="f20-1-network",
    )

    mocker.patch(
        "ironic_understack.port_bios_name_hook.ironic_ports_for_node",
        return_value=[port1, port2],
    )

    PortBiosNameHook().__call__(task, _INVENTORY, {})

    assert port1.pxe_enabled is True
    assert port2.pxe_enabled is False


def test_removing_bios_name(mocker, caplog):
    """Port with unknown MAC gets bios_name removed."""
    caplog.set_level(logging.DEBUG)
    task = _make_task(mocker)

    unknown_port = _make_port(
        mocker,
        "33:33:33:33:33:33",
        extra={"bios_name": "old_name_no_longer_valid"},
        name="original-name",
        physical_network="f20-1-network",
    )
    pxe_port = _make_port(
        mocker,
        "11:11:11:11:11:11",
        pxe_enabled=True,
        physical_network="f20-1-network",
    )

    mocker.patch(
        "ironic_understack.port_bios_name_hook.ironic_ports_for_node",
        return_value=[unknown_port, pxe_port],
    )

    PortBiosNameHook().__call__(task, _INVENTORY, {})

    assert unknown_port.name == "original-name"
    assert "bios_name" not in unknown_port.extra
