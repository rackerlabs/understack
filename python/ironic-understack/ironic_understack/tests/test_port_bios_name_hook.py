import logging

from ironic.common import exception
from oslo_utils import uuidutils

from ironic_understack.port_bios_name_hook import PortBiosNameHook

_INVENTORY = {
    "memory": {"physical_mb": 98304},
    "interfaces": [
        {"mac_address": "11:11:11:11:11:11", "name": "NIC.Integrated.1-1"},
        {"mac_address": "22:22:22:22:22:22", "name": "NIC.Integrated.1-2"},
    ],
}


def _make_task(mocker, bios_value=None, bios_error=None, cache_error=None):
    mock_node = mocker.Mock(id=1234, uuid=uuidutils.generate_uuid())
    mock_node.name = "Dell-CR1MB0"
    task = mocker.Mock(node=mock_node, context=mocker.Mock())

    if cache_error:
        task.driver.bios.cache_bios_settings.side_effect = cache_error
    elif bios_error:
        mocker.patch(
            "ironic_understack.port_bios_name_hook.BIOSSetting.get",
            side_effect=bios_error,
        )
    elif bios_value is not None:
        setting = mocker.Mock(value=bios_value)
        mocker.patch(
            "ironic_understack.port_bios_name_hook.BIOSSetting.get",
            return_value=setting,
        )
    else:
        setting = mocker.Mock(value=None)
        mocker.patch(
            "ironic_understack.port_bios_name_hook.BIOSSetting.get",
            return_value=setting,
        )

    return task


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


def test_pxe_from_bios_setting(mocker, caplog):
    """BIOS HttpDev1Interface determines pxe_enabled."""
    caplog.set_level(logging.DEBUG)
    task = _make_task(mocker, bios_value="NIC.Integrated.1-1-1")

    port1 = _make_port(mocker, "11:11:11:11:11:11")
    port2 = _make_port(mocker, "22:22:22:22:22:22")

    mocker.patch(
        "ironic_understack.port_bios_name_hook.ironic_ports_for_node",
        return_value=[port1, port2],
    )

    PortBiosNameHook().__call__(task, _INVENTORY, {})

    assert port1.pxe_enabled is True
    assert port2.pxe_enabled is False
    assert port1.extra == {"bios_name": "NIC.Integrated.1-1"}
    assert port1.name == "Dell-CR1MB0:NIC.Integrated.1-1"
    assert port1.physical_network == "enrol"


def test_pxe_fallback_when_cache_fails(mocker, caplog):
    """Falls back to heuristic when BIOS cache fails."""
    caplog.set_level(logging.DEBUG)
    task = _make_task(mocker, cache_error=Exception("no BIOS"))

    port1 = _make_port(mocker, "11:11:11:11:11:11")
    port2 = _make_port(mocker, "22:22:22:22:22:22")

    mocker.patch(
        "ironic_understack.port_bios_name_hook.ironic_ports_for_node",
        return_value=[port1, port2],
    )

    PortBiosNameHook().__call__(task, _INVENTORY, {})

    # Heuristic picks NIC.Integrated.1-1 (first sorted match)
    assert port1.pxe_enabled is True
    assert port2.pxe_enabled is False
    assert "falling back to naming heuristic" in caplog.text


def test_pxe_fallback_when_setting_missing(mocker, caplog):
    """Falls back to heuristic when BIOS setting not found."""
    caplog.set_level(logging.DEBUG)
    task = _make_task(
        mocker,
        bios_error=exception.BIOSSettingNotFound(node="fake", name="HttpDev1Interface"),
    )

    port1 = _make_port(mocker, "11:11:11:11:11:11")
    port2 = _make_port(mocker, "22:22:22:22:22:22")

    mocker.patch(
        "ironic_understack.port_bios_name_hook.ironic_ports_for_node",
        return_value=[port1, port2],
    )

    PortBiosNameHook().__call__(task, _INVENTORY, {})

    assert port1.pxe_enabled is True
    assert port2.pxe_enabled is False
    assert "falling back to naming heuristic" in caplog.text


def test_retaining_physical_network(mocker, caplog):
    """Existing physical_network and local_link_connection are preserved."""
    caplog.set_level(logging.DEBUG)
    task = _make_task(mocker, bios_value="NIC.Integrated.1-1-1")

    port = _make_port(
        mocker,
        "11:11:11:11:11:11",
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


def test_clears_pxe_on_previously_enabled_port(mocker, caplog):
    """Port that was pxe_enabled but no longer matches gets cleared."""
    caplog.set_level(logging.DEBUG)
    task = _make_task(mocker, bios_value="NIC.Integrated.1-2-1")

    port1 = _make_port(mocker, "11:11:11:11:11:11", pxe_enabled=True)
    port2 = _make_port(mocker, "22:22:22:22:22:22")

    mocker.patch(
        "ironic_understack.port_bios_name_hook.ironic_ports_for_node",
        return_value=[port1, port2],
    )

    PortBiosNameHook().__call__(task, _INVENTORY, {})

    assert port1.pxe_enabled is False
    assert port2.pxe_enabled is True


def test_removing_bios_name(mocker, caplog):
    """Port with unknown MAC gets bios_name removed."""
    caplog.set_level(logging.DEBUG)
    task = _make_task(mocker, bios_value="NIC.Integrated.1-1-1")

    port = _make_port(
        mocker,
        "33:33:33:33:33:33",
        extra={"bios_name": "old_name_no_longer_valid"},
        name="original-name",
    )

    mocker.patch(
        "ironic_understack.port_bios_name_hook.ironic_ports_for_node",
        return_value=[port],
    )

    PortBiosNameHook().__call__(task, _INVENTORY, {})

    assert port.name == "original-name"
    assert "bios_name" not in port.extra
