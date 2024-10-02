import re
import pytest

from understack_workflows.bmc_chassis_info import ChassisInfo
from understack_workflows.bmc_chassis_info import InterfaceInfo
from understack_workflows import nautobot_device

class FakeNautobot():
    def __init__(self):
        self.graphql = FakeNautobot.Graphql()
        self.dcim = FakeNautobot.Dcim()

    class Graphql():
        def query(self, graphql):
            if "61:80" in graphql:
                return FakeNautobot.GraphqlResponse("f20-3-1.iad3")
            if "32:DF" in graphql:
                return FakeNautobot.GraphqlResponse("f20-3-2.iad3")
            if "10:7F" in graphql:
                return FakeNautobot.GraphqlResponse("f20-3-1d.iad3")
            raise Exception(f"implement graphql faker {graphql}")

    class Dcim():
        def __init__(self):
            self.devices = FakeNautobot.RestApiEndpoint()

    class RestApiEndpoint():
        def create(self, **kw):
            return "new device here"

        def get(self, **kw):
            match kw:
                case {'serial': '33GSW04'}:
                    return None
                case _:
                    raise Exception(f"implement me {kw}")

    class GraphqlResponse():
        def __init__(self, name):
            self.json = {
                "data": {
                    "devices": [
                        {
                            "name": f"{name}.iad3.rackspace.net",
                            "role": {
                                "name": "Tenant leaf"
                            },
                            "location": {
                                "id": "da47f07f-b66a-4f0c-b780-4be8498e6129",
                                "name": "IAD3",
                            },
                            "rack": {
                                "id": "3dd3c0f6-c6cd-42ff-8e34-763d0795ea16",
                                "name": "F20-3",
                            }
                        }
                    ]
                }
            }

def test_find_or_create():
    nautobot = FakeNautobot()
    chassis_info = ChassisInfo(
        manufacturer='Dell Inc.',
        model_number='PowerEdge R7615',
        serial_number='33GSW04',
        bios_version="1.6.10",
        bmc_ip_address='1.2.3.4',
        interfaces=[
            InterfaceInfo(
                name= 'iDRAC',
                description= 'Dedicated iDRAC interface',
                mac_address= 'A8:3C:A5:35:43:86',
                remote_switch_mac_address= 'C4:4D:84:48:61:80',
                remote_switch_port_name= 'GigabitEthernet1/0/3',
            ),
            InterfaceInfo(
                description= 'NIC in Slot 1 Port 1',
                mac_address= '14:23:F3:F5:25:F0',
                name= 'NIC.Slot.1-1',
                remote_switch_mac_address= 'C4:7E:E0:E4:32:DF',
                remote_switch_port_name= 'Ethernet1/6',
            ),
            InterfaceInfo(
                description= 'NIC in Slot 1 Port 2',
                mac_address= '14:23:F3:F5:25:F1',
                name= 'NIC.Slot.1-2',
                remote_switch_mac_address= 'C4:7E:E0:E4:10:7F',
                remote_switch_port_name= 'Ethernet1/6',
            ),
        ]
    )

    assert nautobot_device.find_or_create(chassis_info, nautobot) == "new device here"
