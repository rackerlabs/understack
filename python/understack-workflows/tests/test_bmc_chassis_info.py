import json
import os
import pathlib
from ipaddress import IPv4Address
from ipaddress import IPv4Interface

from understack_workflows import bmc_chassis_info
from understack_workflows.bmc import Bmc


class FakeBmc(Bmc):
    def __init__(self, fixtures):
        self.fixtures = fixtures
        self.ip_address = "1.2.3.4"
        super().__init__(ip_address=self.ip_address)

    def redfish_request(self, path: str, *_args, **_kw) -> dict:
        path = path.replace("/", "_") + ".json"
        return self.fixtures[path]


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
        manufacturer="Dell",
        model_number="PowerEdge R7615",
        serial_number="33GSW04",
        bios_version="1.6.10",
        bmc_ip_address="1.2.3.4",
        power_on=True,
        bmc_interface=bmc_chassis_info.InterfaceInfo(
            name="iDRAC",
            description="Dedicated iDRAC interface",
            mac_address="A8:3C:A5:35:43:86",
            hostname="idrac-33GSW04",
            ipv4_address=IPv4Interface("10.46.96.156/26"),
            ipv4_gateway=IPv4Address("10.46.96.129"),
        ),
        memory_gib=96,
        cpu="AMD EPYC 9124 16-Core Processor",
    )
