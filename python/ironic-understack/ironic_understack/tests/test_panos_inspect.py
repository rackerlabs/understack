from unittest.mock import Mock

import pytest
import requests
from ironic.common import exception
from ironic.common import states

from ironic_understack.drivers import panos_inspect
from ironic_understack.drivers.panos_inspect import PanosInspect
from ironic_understack.utils import panos_api

SYSTEM = {"model": "PA-1410", "serial": "000000000001", "sw-version": "11.0.0"}


@pytest.fixture
def task():
    task = Mock()
    task.node.uuid = "node-uuid"
    task.node.driver_info = {"management_ip": "192.0.2.10"}
    task.node.properties = {}
    task.node.extra = {}
    task.node.traits = []  # Ensure traits is iterable for HA logic
    return task


@pytest.fixture
def client(mocker):
    client = Mock()
    client.login.return_value = "standard"
    client.system_info.return_value = dict(SYSTEM)
    mocker.patch.object(panos_api, "PanosClient", return_value=client)
    # Mock HA-related functions to prevent timeouts in basic tests
    mocker.patch.object(panos_inspect, "_discover_and_update_ports")
    mocker.patch.object(panos_inspect, "_validate_firewall_readiness")
    mocker.patch.object(panos_inspect, "_handle_ha_configuration")
    return client


def test_get_properties_matches_what_validate_reads():
    assert set(PanosInspect().get_properties()) == {"management_ip"}


def test_validate_requires_management_ip(task):
    task.node.driver_info = {}
    with pytest.raises(exception.MissingParameterValue):
        PanosInspect().validate(task)


def test_validate_success(task):
    PanosInspect().validate(task)


def test_inspect_records_system_info(task, client):
    assert PanosInspect().inspect_hardware(task) == states.MANAGEABLE

    panos_api.PanosClient.assert_called_once_with("192.0.2.10")
    assert task.node.properties == {"model": "PA-1410", "firmware_version": "11.0.0"}
    assert task.node.extra == {"serial": "000000000001"}
    task.node.save.assert_called_once()


def test_inspect_keeps_enrolled_model_and_serial(task, client):
    # enroll-fw sets these from Nautobot; inspection does not overwrite them.
    task.node.properties = {"model": "PA-1410-NB", "vendor": "Palo Alto"}
    task.node.extra = {"serial": "nautobot-serial", "mate_serial": "mate"}

    PanosInspect().inspect_hardware(task)

    assert task.node.properties == {
        "model": "PA-1410-NB",
        "vendor": "Palo Alto",
        "firmware_version": "11.0.0",
    }
    assert task.node.extra == {"serial": "nautobot-serial", "mate_serial": "mate"}


@pytest.mark.parametrize(
    "error",
    [panos_api.PanosApiError("rejected"), requests.ConnectionError("unreachable")],
)
def test_inspect_failure(task, client, error):
    client.login.side_effect = error

    with pytest.raises(exception.HardwareInspectionFailure, match=r"192\.0\.2\.10"):
        PanosInspect().inspect_hardware(task)
    task.node.save.assert_not_called()


def test_apply_system_info_ignores_empty_fields(task):
    panos_inspect._apply_system_info(task.node, {"model": "", "serial": ""})
    assert task.node.properties == {}
    assert task.node.extra == {}


@pytest.mark.parametrize(
    ("current", "derived", "expected"),
    [
        ("f20-3-network", None, "f20-3-network"),
        ("f20-3-network", "f20-3/f20-4-network", "f20-3-network"),
        (None, "f20-3-network", "f20-3-network"),
    ],
    ids=["not-wiped", "not-replaced", "filled-in"],
)
def test_existing_port_keeps_its_physical_network(
    task, mocker, current, derived, expected
):
    task.node.name = "fw1"
    macs = {"ethernet1/1": "60:15:2b:54:1a:10", "ethernet1/2": "60:15:2b:54:1a:11"}
    task.ports = [Mock(address=mac, physical_network=current) for mac in macs.values()]
    neighbors = [
        {
            "local_interface": interface,
            "system_name": "f20-3-1.iad3",
            "port_id": f"Ethernet1/{n}",
            "chassis_id": "c4:7e:e0:e4:55:3f",
        }
        for n, interface in enumerate(macs, start=43)
    ]
    mocker.patch.object(
        panos_inspect.vlan_group_name_convention,
        "vlan_group_names",
        return_value={"f20-3-1.iad3": derived},
    )

    panos_inspect._update_ports_from_neighbors(task, neighbors, macs)

    assert [p.physical_network for p in task.ports] == [expected, expected]


def test_switches_for_ports_skips_ports_without_a_switch():
    ports = [
        Mock(local_link_connection={"switch_info": "leaf-1"}),
        Mock(local_link_connection={"switch_info": "leaf-1"}),
        Mock(local_link_connection={"switch_info": "None"}),
        Mock(local_link_connection={}),
        Mock(local_link_connection=None),
    ]

    assert panos_inspect._switches_for_ports(ports) == {"leaf-1"}


@pytest.mark.parametrize(
    ("hsci_speed", "warns"),
    [("10G", True), ("25000", False), ("unknown", False)],
    ids=["slower", "same", "unparsable"],
)
def test_warns_only_when_hsci_is_slower_than_data_ports(mocker, hsci_speed, warns):
    log = mocker.patch.object(panos_inspect, "LOG")
    ports = [Mock(local_link_connection={"port_speed": "25000"})]

    panos_inspect._warn_if_hsci_slower("n1", ports, {"hsci": {"speed": hsci_speed}})

    assert log.warning.called is warns


def _ha_status(serial, conn):
    return {"peer": {"serial": serial, "conn_status": conn}}


def _ha_pair(
    mocker,
    task,
    *,
    hsci="up",
    peer=("S2", "up"),
    mate_peer=("S1", "up"),
    mate_switch="leaf-2",
):
    """A primary, its secondary in Ironic and both devices; returns this device."""
    task.node.traits = ["CUSTOM_PRIMARY"]
    task.node.extra = {"serial": "S1", "mate_serial": "S2"}
    task.node.resource_class = "pa1410"
    task.ports = [Mock(local_link_connection={"switch_info": "leaf-1"})]
    mate = Mock(
        id=2,
        uuid="mate-uuid",
        traits=["CUSTOM_SECONDARY"],
        extra={"serial": "S2", "mate_serial": "S1"},
        resource_class="pa1410",
        driver_info={"management_ip": "192.0.2.11"},
    )
    mocker.patch("ironic.objects.node.Node.list", return_value=[mate])
    mocker.patch.object(
        panos_inspect.port.Port,
        "list_by_node_id",
        return_value=[Mock(local_link_connection={"switch_info": mate_switch})],
    )
    device = Mock()
    device.get_ha_interface_status.return_value = {
        "ha1-a": {"state": "up"},
        "ha1-b": {"state": "up"},
        "hsci": {"state": hsci},
    }
    device.get_ha_status.return_value = _ha_status(*peer)
    mate_device = mocker.patch.object(panos_api, "PanosClient").return_value
    mate_device.get_ha_status.return_value = _ha_status(*mate_peer)
    return device


def _validate_ha(task, device):
    """Run the real HA checks; return the node they saved."""
    node = task.node
    panos_inspect._validate_and_pair_ha(
        task, device, node, dict(node.extra), "S2", "primary"
    )
    node.save.assert_called_once()
    return node


def test_a_healthy_pair_is_operational(mocker, task):
    device = _ha_pair(mocker, task)
    task.node.last_error = "stale"

    node = _validate_ha(task, device)

    assert node.extra["ha_operational"] is True
    assert node.last_error is None


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"peer": ("S2", "down")}, "HA peer connection not up"),
        ({"mate_peer": ("S9", "up")}, "Mate peer serial mismatch"),
        ({"mate_peer": ("S1", "down")}, "Mate peer connection not up"),
    ],
    ids=["peer-down", "mate-sees-other", "mate-down"],
)
def test_an_unhealthy_pair_is_not_operational(mocker, task, change, reason):
    device = _ha_pair(mocker, task, **change)

    node = _validate_ha(task, device)

    assert node.extra["ha_operational"] is False
    assert reason in node.last_error


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"peer": ("S9", "up")}, "HA peer serial mismatch"),
        ({"mate_switch": "leaf-1"}, "same switch"),
    ],
    ids=["wrong-peer", "same-switch"],
)
def test_a_cabling_fault_fails_inspection(mocker, task, change, reason):
    device = _ha_pair(mocker, task, **change)

    with pytest.raises(exception.HardwareInspectionFailure, match=reason):
        _validate_ha(task, device)

    assert task.node.extra["ha_operational"] is False
    assert reason in task.node.last_error
    task.node.save.assert_called_once()


def test_a_local_link_down_never_contacts_the_mate(mocker, task):
    device = _ha_pair(mocker, task, hsci="down")

    node = _validate_ha(task, device)

    assert node.extra["ha_operational"] is False
    assert "HA interfaces not all up" in node.last_error
    panos_api.PanosClient.assert_not_called()


def test_a_device_timeout_is_recorded_not_raised(mocker, task):
    device = _ha_pair(mocker, task)
    device.get_ha_status.side_effect = requests.Timeout("read timed out")

    node = _validate_ha(task, device)

    assert node.extra["ha_operational"] is False
    assert node.last_error == "read timed out"
