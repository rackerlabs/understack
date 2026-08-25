import pytest

from understack_workflows.dcx import enroll as dcx_enroll
from understack_workflows.dcx.client import DcxClient

DEVICE_NUMBER = 1383170

# Shaped like GET /devices/{id}/switch_ports: one DRACNet (management) port and
# two Public (25G data) ports on a switch pair.
SWITCH_PORTS = [
    {
        "switch_port": {
            "name": "fa0/10",
            "vlans": [],
            "native_vlan": None,
            "interface_type": "DRACNet",
            "port_number": 10,
            "switch_name": "f8-41-1d.iad3",
        }
    },
    {
        "switch_port": {
            "name": "fa0/1",
            "vlans": [3800],
            "native_vlan": 3800,
            "interface_type": "Public",
            "port_number": 1,
            "switch_name": "f8-41-2.iad3",
        }
    },
    {
        "switch_port": {
            "name": "fa0/16",
            "vlans": [],
            "native_vlan": 1,
            "interface_type": "Public",
            "port_number": 16,
            "switch_name": "f8-42-2.iad3",
        }
    },
]

# Shaped like GET /devices/locations_and_ports?device_numbers={id}
LOCATION = {
    "device_number": str(DEVICE_NUMBER),
    "container": "F8-41",
    "starting_space": "19.0",
    "data_center": "IAD3",
}


def build():
    return dcx_enroll.build_enroll_kwargs(
        # argparse hands us the device number as a string; enroll should coerce
        # external_cmdb_id back to an int.
        device_number=str(DEVICE_NUMBER),
        switch_ports=SWITCH_PORTS,
        location=LOCATION,
        name_prefix="Appliance",
    )


def test_node_name_and_cmdb_and_resource_class():
    kwargs = build()
    assert kwargs["name"] == "Appliance-1383170"
    assert kwargs["external_cmdb_id"] == DEVICE_NUMBER
    assert kwargs["resource_class"] == "appliance"


def test_only_public_ports_are_enrolled():
    kwargs = build()
    interfaces = {port["intf"] for port in kwargs["ports"]}
    # DRACNet (Ethernet1/10) is excluded; only the two Public ports remain.
    assert interfaces == {"Ethernet1/1", "Ethernet1/16"}
    assert len(kwargs["ports"]) == 2


def test_port_fields():
    kwargs = build()
    by_switch = {port["switch"]: port for port in kwargs["ports"]}

    # switch_info is the fully-qualified switch name.
    port = by_switch["f8-41-2.iad3.rackspace.net"]
    assert port["label"] == "fa0/1"
    assert port["intf"] == "Ethernet1/1"

    port = by_switch["f8-42-2.iad3.rackspace.net"]
    assert port["label"] == "fa0/16"
    assert port["intf"] == "Ethernet1/16"


def test_physical_network_is_derived():
    kwargs = build()
    # The data switches are a -2 pair, so the suffix is kept in the group name.
    assert kwargs["physical_network"] == "f8-41-2/f8-42-2-network"


@pytest.mark.parametrize(
    ("switch_names", "expected"),
    [
        (["f8-40-1.iad3", "f8-40-2.iad3"], "f8-40-network"),
        (["f8-41-1.iad3", "f8-42-1.iad3"], "f8-41/f8-42-network"),
        (["f8-41-2.iad3", "f8-42-2.iad3"], "f8-41-2/f8-42-2-network"),
        (["f8-41-3.iad3", "f8-42-3.iad3"], "f8-41-3/f8-42-3-network"),
    ],
)
def test_derive_physnet(switch_names, expected):
    assert dcx_enroll.derive_physnet(switch_names) == expected


def test_physical_network_override():
    kwargs = dcx_enroll.build_enroll_kwargs(
        device_number=DEVICE_NUMBER,
        switch_ports=SWITCH_PORTS,
        location=LOCATION,
        name_prefix="Appliance",
        physical_network="custom-network",
    )
    assert kwargs["physical_network"] == "custom-network"


def test_resource_class_override():
    kwargs = dcx_enroll.build_enroll_kwargs(
        device_number=DEVICE_NUMBER,
        switch_ports=SWITCH_PORTS,
        location=LOCATION,
        name_prefix="Appliance",
        resource_class="special",
    )
    assert kwargs["resource_class"] == "special"


def test_extra_carries_rack_and_position():
    kwargs = build()
    assert kwargs["extra"] == {
        "external_cmdb_id": DEVICE_NUMBER,
        "rack": "F8-41",
        "position": 19,
    }


def test_no_public_ports_raises():
    with pytest.raises(ValueError, match="no Public switch ports"):
        dcx_enroll.build_enroll_kwargs(
            device_number=DEVICE_NUMBER,
            switch_ports=[SWITCH_PORTS[0]],
            location=LOCATION,
            name_prefix="Appliance",
        )


def test_deterministic_mac_is_stable_and_locally_administered():
    mac1 = dcx_enroll.deterministic_mac(DEVICE_NUMBER, "f8-41-2.iad3", 1)
    mac2 = dcx_enroll.deterministic_mac(DEVICE_NUMBER, "f8-41-2.iad3", 1)
    assert mac1 == mac2

    first_octet = int(mac1.split(":")[0], 16)
    assert first_octet & 0x01 == 0  # unicast
    assert first_octet & 0x02 == 0x02  # locally administered


def test_deterministic_mac_is_unique_per_port():
    mac1 = dcx_enroll.deterministic_mac(DEVICE_NUMBER, "f8-41-2.iad3", 1)
    mac2 = dcx_enroll.deterministic_mac(DEVICE_NUMBER, "f8-42-2.iad3", 16)
    assert mac1 != mac2


def test_macs_reproducible_across_builds():
    assert build()["ports"] == build()["ports"]


def test_rack_of():
    assert dcx_enroll.rack_of("f8-41-2.iad3") == "f8-41"


def test_rack_of_bad_name_raises():
    with pytest.raises(ValueError, match="Unexpected switch name"):
        dcx_enroll.rack_of("nodashes")


def test_dcx_client_switch_ports(requests_mock):
    client = DcxClient(auth_token="secret", api_url="https://dcx.example")
    requests_mock.get(
        "https://dcx.example/devices/1383170/switch_ports",
        json=SWITCH_PORTS,
    )
    assert client.switch_ports(1383170) == SWITCH_PORTS
    assert requests_mock.last_request.headers["X-Auth-Token"] == "secret"


def test_dcx_client_location(requests_mock):
    client = DcxClient(auth_token="secret", api_url="https://dcx.example")
    requests_mock.get(
        "https://dcx.example/devices/locations_and_ports",
        json=[LOCATION],
    )
    assert client.location(1383170) == LOCATION
    assert requests_mock.last_request.qs["device_numbers"] == ["1383170"]


def test_dcx_client_location_empty_raises(requests_mock):
    client = DcxClient(auth_token="secret", api_url="https://dcx.example")
    requests_mock.get(
        "https://dcx.example/devices/locations_and_ports",
        json=[],
    )
    with pytest.raises(ValueError, match="no location"):
        client.location(1383170)


class FakeDcxClient(DcxClient):
    def __init__(self):
        pass

    def switch_ports(self, device_number):
        return SWITCH_PORTS

    def location(self, device_number):
        return LOCATION


def test_enroll_from_dcx_calls_reconciler(monkeypatch):
    captured = {}

    def fake_enroll(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(dcx_enroll.netdev_reconciler, "enroll", fake_enroll)

    result = dcx_enroll.enroll_from_dcx(
        client=FakeDcxClient(),
        device_number=DEVICE_NUMBER,
        name_prefix="Appliance",
    )

    assert captured == result
    assert captured["name"] == "Appliance-1383170"
    assert captured["physical_network"] == "f8-41-2/f8-42-2-network"
    assert len(captured["ports"]) == 2


def test_enroll_from_dcx_dry_run_does_not_enroll(monkeypatch):
    def fail_enroll(**kwargs):
        raise AssertionError("enroll must not be called on a dry run")

    monkeypatch.setattr(dcx_enroll.netdev_reconciler, "enroll", fail_enroll)

    result = dcx_enroll.enroll_from_dcx(
        client=FakeDcxClient(),
        device_number=DEVICE_NUMBER,
        name_prefix="Appliance",
        dry_run=True,
    )

    assert result["name"] == "Appliance-1383170"
