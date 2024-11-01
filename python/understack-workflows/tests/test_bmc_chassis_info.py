import json
import os
import pathlib
from ipaddress import IPv4Address
from ipaddress import IPv4Interface

from understack_workflows import bmc_chassis_info

FIXTURE_PATH = "json_samples/bmc_chassis_info"


class FakeBmc:
    def __init__(self, fixtures):
        self.fixtures = fixtures
        self.ip_address = "1.2.3.4"

    def redfish_request(self, path: str) -> dict:
        path = path.replace("/", "_") + ".json"
        return self.fixtures[path]


def redfish_fixtures_by_platform() -> dict:
    return {
        platform: read_fixtures(FIXTURE_PATH.joinpath(platform))
        for platform in sorted(os.listdir(FIXTURE_PATH))
    }


def read_fixtures(path) -> dict:
    path = pathlib.Path(__file__).parent.joinpath(path)
    return {
        filename: read_fixture(path, filename)
        for filename in sorted(os.listdir(path))
        if filename.endswith("json")
    }


def read_fixture(path, filename):
    with path.joinpath(filename).open("r") as f:
        return json.loads(f.read())


def test_chassis_info_R7615():
    bmc = FakeBmc(read_fixtures("json_samples/bmc_chassis_info/R7615"))
    assert bmc_chassis_info.chassis_info(bmc) == bmc_chassis_info.ChassisInfo(
        manufacturer="Dell Inc.",
        model_number="PowerEdge R7615",
        serial_number="33GSW04",
        bios_version="1.6.10",
        bmc_ip_address="1.2.3.4",
        interfaces=[
            bmc_chassis_info.InterfaceInfo(
                name="iDRAC",
                description="Dedicated iDRAC interface",
                mac_address="A8:3C:A5:35:43:86",
                ipv4_address=IPv4Interface("10.46.96.156/26"),
                ipv4_gateway=IPv4Address("10.46.96.129"),
                remote_switch_mac_address="C4:4D:84:48:61:80",
                remote_switch_port_name="GigabitEthernet1/0/3",
            ),
            bmc_chassis_info.InterfaceInfo(
                name="NIC.Integrated.1-1",
                description="Integrated NIC 1 Port 1",
                mac_address="D4:04:E6:4F:8D:B4",
                remote_switch_mac_address="C4:7E:E0:E4:10:7F",
                remote_switch_port_name="Ethernet1/5",
            ),
            bmc_chassis_info.InterfaceInfo(
                name="NIC.Integrated.1-2",
                description="Integrated NIC 1 Port 2",
                mac_address="D4:04:E6:4F:8D:B5",
                remote_switch_mac_address="C4:7E:E0:E4:32:DF",
                remote_switch_port_name="Ethernet1/5",
            ),
            bmc_chassis_info.InterfaceInfo(
                description="NIC in Slot 1 Port 1",
                mac_address="14:23:F3:F5:25:F0",
                name="NIC.Slot.1-1",
                remote_switch_mac_address="C4:7E:E0:E4:32:DF",
                remote_switch_port_name="Ethernet1/6",
            ),
            bmc_chassis_info.InterfaceInfo(
                description="NIC in Slot 1 Port 2",
                mac_address="14:23:F3:F5:25:F1",
                name="NIC.Slot.1-2",
                remote_switch_mac_address="C4:7E:E0:E4:10:7F",
                remote_switch_port_name="Ethernet1/6",
            ),
        ],
    )
