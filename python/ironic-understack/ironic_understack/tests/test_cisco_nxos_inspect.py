from unittest.mock import MagicMock
from unittest.mock import Mock

import pytest
import requests
from ironic.common import exception
from ironic.common import states

from ironic_understack.drivers import cisco_nxos_inspect
from ironic_understack.drivers.cisco_nxos_inspect import CiscoNxosInspect
from ironic_understack.utils import nxos_api

VERSION = {
    "nxos_ver_str": "10.3(4a)",
    "chassis_id": "Nexus9000 C93180YC-FX Chassis",
    "proc_board_id": "FDO00000001",
}
SHOW_INTERFACE = {
    "TABLE_interface": {
        "ROW_interface": [
            {"interface": "Ethernet1/1", "eth_bia_addr": "00de.fb00.0101"},
            {"interface": "Ethernet1/2", "eth_bia_addr": "00de.fb00.0102"},
        ]
    }
}
SHOW_VDC = {"TABLE_vdc": {"ROW_vdc": {"vdc_id": "1", "mac": "00de.fb00.0000"}}}


@pytest.fixture
def task():
    task = Mock()
    task.node.id = 3
    task.node.uuid = "node-uuid"
    task.node.name = "f20-3-1"
    task.node.driver_info = {
        "nxos_address": "192.0.2.20",
        "nxos_username": "svc",
        "nxos_password": "example-pw",
    }
    task.node.properties = {}
    task.node.extra = {}
    task.ports = []
    return task


@pytest.fixture
def client(mocker):
    client = MagicMock()
    client.__enter__.return_value = client
    client.show_many.return_value = [dict(VERSION), SHOW_INTERFACE, SHOW_VDC]
    client.show_text.return_value = "feature lldp\n"
    mocker.patch.object(nxos_api, "NxosClient", return_value=client)
    mocker.patch.object(cisco_nxos_inspect.cisco_nxos_firmware, "record_versions")
    return client


def _switch_reports(client, version=None, interface=None, vdc=None):
    """Replace one or more of the batched command outputs."""
    current = client.show_many.return_value
    client.show_many.return_value = [
        current[0] if version is None else version,
        current[1] if interface is None else interface,
        current[2] if vdc is None else vdc,
    ]


@pytest.fixture(autouse=True)
def store(mocker):
    return mocker.patch.object(
        cisco_nxos_inspect.inspect_utils, "store_inspection_data"
    )


@pytest.fixture
def port_cls(mocker):
    return mocker.patch.object(cisco_nxos_inspect.port, "Port")


def _existing(name, address):
    p = Mock(address=address)
    p.name = name
    return p


def test_validate_requires_nxos_address(task):
    task.node.driver_info = {}
    with pytest.raises(exception.MissingParameterValue):
        CiscoNxosInspect().validate(task)


def test_inspect_creates_a_port_per_interface(task, client, port_cls):
    assert CiscoNxosInspect().inspect_hardware(task) == states.MANAGEABLE

    nxos_api.NxosClient.assert_called_once_with(
        "192.0.2.20", "svc", "example-pw", verify=False
    )
    client.show_many.assert_called_once_with(
        ["show version", "show interface", "show vdc detail"]
    )
    client.show_text.assert_called_once_with("show running-config lldp")
    client.__exit__.assert_called_once()
    assert [c.kwargs for c in port_cls.call_args_list] == [
        {
            "node_id": 3,
            "address": "00:de:fb:00:01:01",
            "name": "f20-3-1:Ethernet1/1",
            "pxe_enabled": False,
        },
        {
            "node_id": 3,
            "address": "00:de:fb:00:01:02",
            "name": "f20-3-1:Ethernet1/2",
            "pxe_enabled": False,
        },
    ]
    assert port_cls.return_value.create.call_count == 2
    # Make, model and serial go only in the inspection data.
    assert task.node.properties == {"chassis_mac": "00:de:fb:00:00:00"}
    assert task.node.extra == {}
    cisco_nxos_inspect.cisco_nxos_firmware.record_versions.assert_called_once_with(
        task, VERSION
    )
    assert task.ports is None
    task.node.save.assert_called_once()


def test_inspect_stores_inspection_data(task, client, port_cls, store):
    client.show_text.return_value = "feature lldp\nlldp chassis-id switch\n"

    CiscoNxosInspect().inspect_hardware(task)

    store.assert_called_once_with(
        task.node,
        {
            "interfaces": [
                {"name": "Ethernet1/1", "mac_address": "00:de:fb:00:01:01"},
                {"name": "Ethernet1/2", "mac_address": "00:de:fb:00:01:02"},
            ],
            "system_vendor": {
                "manufacturer": "Cisco Systems, Inc.",
                "product_name": "Nexus9000 C93180YC-FX Chassis",
                "serial_number": "FDO00000001",
            },
        },
        {
            "nxos_version": "10.3(4a)",
            "chassis_mac": "00:de:fb:00:00:00",
            "lldp_chassis_id": "switch",
        },
        task.context,
    )


def test_unreadable_lldp_setting_does_not_fail_inspection(
    task, client, port_cls, store
):
    client.show_text.side_effect = nxos_api.NxosApiError("HTTP 500: not JSON")

    assert CiscoNxosInspect().inspect_hardware(task) == states.MANAGEABLE
    assert store.call_args.args[2]["lldp_chassis_id"] is None


@pytest.mark.parametrize(
    "vdc",
    [
        {},
        nxos_api.NxosApiError("'show vdc detail': % Invalid command"),
        {"TABLE_vdc": {"ROW_vdc": {"vdc_id": "1", "max_mac": 100}}},
    ],
    ids=["not-reported", "unsupported", "no-mac-field"],
)
def test_missing_chassis_mac_does_not_fail_inspection(task, client, port_cls, vdc):
    _switch_reports(client, vdc=vdc)

    assert CiscoNxosInspect().inspect_hardware(task) == states.MANAGEABLE
    assert "chassis_mac" not in task.node.properties
    assert port_cls.return_value.create.call_count == 2


def test_unreachable_switch_for_lldp_setting_fails_inspection(task, client, port_cls):
    client.show_text.side_effect = requests.ConnectionError("unreachable")

    with pytest.raises(exception.HardwareInspectionFailure):
        CiscoNxosInspect().inspect_hardware(task)


def test_no_firmware_version_does_not_fail_inspection(task, client, port_cls):
    record = cisco_nxos_inspect.cisco_nxos_firmware.record_versions
    record.side_effect = exception.UnsupportedDriverExtension(
        driver="cisco_nxos", extension="firmware components"
    )

    assert CiscoNxosInspect().inspect_hardware(task) == states.MANAGEABLE
    task.node.save.assert_called_once()


def test_existing_port_gets_its_mac_corrected(task, client, port_cls):
    stale = _existing("f20-3-1:Ethernet1/1", "00:DE:FB:00:00:00")
    same = _existing("f20-3-1:Ethernet1/2", "00:DE:FB:00:01:02")
    task.ports = [stale, same]

    CiscoNxosInspect().inspect_hardware(task)

    assert stale.address == "00:de:fb:00:01:01"
    stale.save.assert_called_once()
    same.save.assert_not_called()
    port_cls.assert_not_called()


def test_port_with_the_mac_under_another_name_is_left_alone(task, client, port_cls):
    other = _existing("f20-3-1:uplink", "00:de:fb:00:01:01")
    task.ports = [other]

    CiscoNxosInspect().inspect_hardware(task)

    other.save.assert_not_called()
    assert [c.kwargs["name"] for c in port_cls.call_args_list] == [
        "f20-3-1:Ethernet1/2"
    ]


def test_ports_are_never_deleted(task, client, port_cls):
    gone = _existing("f20-3-1:Ethernet1/48", "00:de:fb:00:01:48")
    task.ports = [gone]

    CiscoNxosInspect().inspect_hardware(task)

    gone.destroy.assert_not_called()


def test_mac_on_another_node_skips_that_port(task, client, port_cls):
    port_cls.return_value.create.side_effect = [
        exception.MACAlreadyExists(mac="00:de:fb:00:01:01"),
        None,
    ]

    assert CiscoNxosInspect().inspect_hardware(task) == states.MANAGEABLE
    assert port_cls.return_value.create.call_count == 2


def test_unnamed_node_uses_uuid_in_port_names(task, client, port_cls):
    task.node.name = None
    CiscoNxosInspect().inspect_hardware(task)
    assert port_cls.call_args_list[0].kwargs["name"] == "node-uuid:Ethernet1/1"


@pytest.mark.parametrize(
    "error",
    [nxos_api.NxosApiError("rejected"), requests.ConnectionError("unreachable")],
)
def test_inspect_failure(task, client, port_cls, error):
    client.show_many.side_effect = error

    with pytest.raises(exception.HardwareInspectionFailure, match=r"192\.0\.2\.20"):
        CiscoNxosInspect().inspect_hardware(task)
    port_cls.assert_not_called()
    task.node.save.assert_not_called()


@pytest.mark.parametrize("failed", ["version", "interface"])
def test_failed_required_command_fails_inspection(task, client, port_cls, failed):
    _switch_reports(client, **{failed: nxos_api.NxosApiError(f"{failed} failed")})

    with pytest.raises(exception.HardwareInspectionFailure, match=f"{failed} failed"):
        CiscoNxosInspect().inspect_hardware(task)
    port_cls.assert_not_called()


def test_system_vendor_uses_the_reported_manufacturer():
    assert cisco_nxos_inspect.system_vendor(
        {**VERSION, "manufacturer": "Cisco Systems Inc"}
    ) == {
        "manufacturer": "Cisco Systems Inc",
        "product_name": "Nexus9000 C93180YC-FX Chassis",
        "serial_number": "FDO00000001",
    }


def test_system_vendor_leaves_out_what_is_not_reported(task, client, port_cls, store):
    _switch_reports(client, version={"nxos_ver_str": "10.3(4a)"})

    CiscoNxosInspect().inspect_hardware(task)

    inventory = store.call_args.args[1]
    assert inventory["system_vendor"] == {"manufacturer": "Cisco Systems, Inc."}


def test_port_without_an_address_gets_one(task, client, port_cls):
    blank = _existing("f20-3-1:Ethernet1/1", None)
    task.ports = [blank]

    CiscoNxosInspect().inspect_hardware(task)

    assert blank.address == "00:de:fb:00:01:01"
    blank.save.assert_called_once()


def test_swapped_macs_are_not_corrected(task, client, port_cls):
    # Each MAC the switch reports is still held by the other port, so either
    # save would violate MAC uniqueness; both are left for an operator.
    one = _existing("f20-3-1:Ethernet1/1", "00:de:fb:00:01:02")
    two = _existing("f20-3-1:Ethernet1/2", "00:de:fb:00:01:01")
    task.ports = [one, two]

    assert CiscoNxosInspect().inspect_hardware(task) == states.MANAGEABLE

    assert one.address == "00:de:fb:00:01:02"
    assert two.address == "00:de:fb:00:01:01"
    one.save.assert_not_called()
    two.save.assert_not_called()


def test_correction_to_a_mac_on_another_node_is_rolled_back(task, client, port_cls):
    stale = _existing("f20-3-1:Ethernet1/1", "00:de:fb:00:00:99")
    stale.save.side_effect = exception.MACAlreadyExists(mac="00:de:fb:00:01:01")
    task.ports = [stale]

    assert CiscoNxosInspect().inspect_hardware(task) == states.MANAGEABLE
    assert stale.address == "00:de:fb:00:00:99"


def test_corrected_mac_is_seen_by_later_interfaces(task, client, port_cls):
    # Ethernet1/1 moves from M0 to M1; Ethernet1/2 then reports M0, which is
    # free again, so it gets a port; a third interface reporting M1 does not.
    _switch_reports(
        client,
        interface={
            "TABLE_interface": {
                "ROW_interface": [
                    {"interface": "Ethernet1/1", "eth_bia_addr": "00de.fb00.0101"},
                    {"interface": "Ethernet1/2", "eth_bia_addr": "00de.fb00.0100"},
                    {"interface": "Ethernet1/3", "eth_bia_addr": "00de.fb00.0101"},
                ]
            }
        },
    )
    moved = _existing("f20-3-1:Ethernet1/1", "00:de:fb:00:01:00")
    task.ports = [moved]

    CiscoNxosInspect().inspect_hardware(task)

    assert moved.address == "00:de:fb:00:01:01"
    assert [c.kwargs["name"] for c in port_cls.call_args_list] == [
        "f20-3-1:Ethernet1/2"
    ]


def test_name_taken_by_another_node_skips_that_port(task, client, port_cls):
    port_cls.return_value.create.side_effect = [
        exception.PortDuplicateName(name="f20-3-1:Ethernet1/1"),
        None,
    ]

    assert CiscoNxosInspect().inspect_hardware(task) == states.MANAGEABLE
    assert port_cls.return_value.create.call_count == 2
