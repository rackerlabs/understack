import json
import pathlib

from understack_workflows import nautobot_device
from understack_workflows.bmc_chassis_info import ChassisInfo
from understack_workflows.bmc_chassis_info import InterfaceInfo
from understack_workflows.nautobot_device import NautobotDevice
from understack_workflows.nautobot_device import NautobotInterface


def read_json_samples(file_path):
    here = pathlib.Path(__file__).parent
    ref = here.joinpath(file_path)
    with ref.open("r") as f:
        return json.loads(f.read())


class FakeNautobot:
    def __init__(self):
        self.graphql = FakeNautobot.Graphql()
        self.dcim = FakeNautobot.Dcim()

    class ApiRecord:
        def __init__(self):
            self.id = "qwerty-1234-qwerty-1234"

        def update(self, *_):
            pass

    class Graphql:
        def query(self, graphql):
            if "61:80" in graphql:
                return FakeNautobot.SwitchResponse()
            if "33GSW04" in graphql:
                return FakeNautobot.GraphqlResponse(
                    "json_samples/bmc_chassis_info/R7615/nautobot_graphql_response_server_device_33GSW04.json"
                )
            raise Exception(f"implement graphql faker {graphql}")

    class Dcim:
        def __init__(self):
            self.devices = FakeNautobot.RestApiEndpoint()
            self.interfaces = FakeNautobot.RestApiEndpoint()
            self.cables = FakeNautobot.RestApiEndpoint()

    class RestApiEndpoint:
        def create(self, **kw):
            return FakeNautobot.ApiRecord()

        def get(self, **kw):
            match kw:
                case {"serial": "33GSW04"}:
                    return None
                case {"device": "qwerty-1234-qwerty-1234", "name": "iDRAC"}:
                    return None
                case _:
                    return FakeNautobot.ApiRecord()

    class GraphqlResponse:
        def __init__(self, name):
            self.json = read_json_samples(name)

    class SwitchResponse:
        def __init__(self):
            self.json = {
                "data": {
                    "devices": [
                        {
                            "id": "leafsw-1234-3456-1234",
                            "name": "f20-3-1.iad3.iad3.rackspace.net",
                            "mac": "C4:7E:E0:E4:32:DF",
                            "role": {"name": "Tenant leaf"},
                            "location": {
                                "id": "da47f07f-b66a-4f0c-b780-4be8498e6129",
                                "name": "IAD3",
                            },
                            "rack": {
                                "id": "3dd3c0f6-c6cd-42ff-8e34-763d0795ea16",
                                "name": "F20-3",
                            },
                        },
                        {
                            "id": "leafsw-1234-3456-1234",
                            "name": "f20-3-2.iad3.iad3.rackspace.net",
                            "mac": "C4:7E:E0:E4:10:7F",
                            "role": {"name": "Tenant leaf"},
                            "location": {
                                "id": "da47f07f-b66a-4f0c-b780-4be8498e6129",
                                "name": "IAD3",
                            },
                            "rack": {
                                "id": "3dd3c0f6-c6cd-42ff-8e34-763d0795ea16",
                                "name": "F20-3",
                            },
                        },
                        {
                            "id": "leafsw-1234-3456-1234",
                            "name": "f20-3-1d.iad3.iad3.rackspace.net",
                            "mac": "C4:4D:84:48:61:80",
                            "role": {"name": "Tenant leaf"},
                            "location": {
                                "id": "da47f07f-b66a-4f0c-b780-4be8498e6129",
                                "name": "IAD3",
                            },
                            "rack": {
                                "id": "3dd3c0f6-c6cd-42ff-8e34-763d0795ea16",
                                "name": "F20-3",
                            },
                        },
                    ]
                }
            }


def test_find_or_create():
    nautobot = FakeNautobot()
    chassis_info = ChassisInfo(
        manufacturer="Dell Inc.",
        model_number="PowerEdge R7615",
        serial_number="33GSW04",
        bios_version="1.6.10",
        bmc_ip_address="1.2.3.4",
        interfaces=[
            InterfaceInfo(
                name="iDRAC",
                description="Dedicated iDRAC interface",
                mac_address="A8:3C:A5:35:43:86",
                remote_switch_mac_address="C4:4D:84:48:61:83",
                remote_switch_port_name="GigabitEthernet1/0/3",
            ),
            InterfaceInfo(
                description="NIC in Slot 1 Port 1",
                mac_address="14:23:F3:F5:25:F0",
                name="NIC.Slot.1-1",
                remote_switch_mac_address="C4:7E:E0:E4:32:DF",
                remote_switch_port_name="Ethernet1/6",
            ),
            InterfaceInfo(
                description="NIC in Slot 1 Port 2",
                mac_address="14:23:F3:F5:25:F1",
                name="NIC.Slot.1-2",
                remote_switch_mac_address="C4:7E:E0:E4:10:7F",
                remote_switch_port_name="Ethernet1/6",
            ),
        ],
    )

    device = nautobot_device.find_or_create(chassis_info, nautobot)

    assert device == NautobotDevice(
        id="a3a2983f-d906-4663-943c-c41ab73c9b62",
        name="Dell-33GSW04",
        location_id="da47f07f-b66a-4f0c-b780-4be8498e6129",
        location_name="IAD3",
        rack_id="1ccd4b4a-7ba3-4557-b1ad-1ba87aee96a6",
        rack_name="F20-2",
        interfaces=[
            NautobotInterface(
                id="ac2f1eae-188e-4fc6-9245-f9a6cf8b4ea8",
                name="NIC.Integrated.1-1",
                type="A_25GBASE_X_SFP28",
                description="Integrated NIC 1 Port 1",
                mac_address="D4:04:E6:4F:8D:B4",
                status="Active",
                ip_address=[],
                neighbor_device_id="275ef491-2b27-4d1b-bd45-330bd6b7e0cf",
                neighbor_device_name="f20-2-1.iad3.rackspace.net",
                neighbor_interface_id="f9a5cc87-d10a-4827-99e8-48961fd1d773",
                neighbor_interface_name="Ethernet1/5",
                neighbor_chassis_mac="9C:54:16:F5:AB:27",
                neighbor_location_name="IAD3",
                neighbor_rack_name="F20-2",
            ),
            NautobotInterface(
                id="39d98f09-3199-40e0-87dc-e5ed6dce78e5",
                name="NIC.Integrated.1-2",
                type="A_25GBASE_X_SFP28",
                description="Integrated NIC 1 Port 2",
                mac_address="D4:04:E6:4F:8D:B5",
                status="Active",
                ip_address=[],
                neighbor_device_id="05f6715a-4dbe-4fd6-af20-1e73adb285c2",
                neighbor_device_name="f20-2-2.iad3.rackspace.net",
                neighbor_interface_id="2148cf50-f70e-42c9-9f68-8ce98d61498c",
                neighbor_interface_name="Ethernet1/5",
                neighbor_chassis_mac="9C:54:16:F5:AC:27",
                neighbor_location_name="IAD3",
                neighbor_rack_name="F20-2",
            ),
            NautobotInterface(
                id="7ac587c4-015b-4a0e-b579-91284cbd0406",
                name="NIC.Slot.1-1",
                type="A_25GBASE_X_SFP28",
                description="NIC in Slot 1 Port 1",
                mac_address="14:23:F3:F5:25:F0",
                status="Active",
                ip_address=[],
                neighbor_device_id="05f6715a-4dbe-4fd6-af20-1e73adb285c2",
                neighbor_device_name="f20-2-2.iad3.rackspace.net",
                neighbor_interface_id="f72bb830-3f3c-4aba-b7d5-9680ea4d358e",
                neighbor_interface_name="Ethernet1/6",
                neighbor_chassis_mac="9C:54:16:F5:AD:27",
                neighbor_location_name="IAD3",
                neighbor_rack_name="F20-2",
            ),
            NautobotInterface(
                id="8c28941c-02cd-4aad-9e3f-93c39e08b58a",
                name="NIC.Slot.1-2",
                type="A_25GBASE_X_SFP28",
                description="NIC in Slot 1 Port 2",
                mac_address="14:23:F3:F5:25:F1",
                status="Active",
                ip_address=[],
                neighbor_device_id="275ef491-2b27-4d1b-bd45-330bd6b7e0cf",
                neighbor_device_name="f20-2-1.iad3.rackspace.net",
                neighbor_interface_id="c210be75-1038-4ba3-9923-60050e1c5362",
                neighbor_interface_name="Ethernet1/6",
                neighbor_chassis_mac="9C:54:16:F5:AD:27",
                neighbor_location_name="IAD3",
                neighbor_rack_name="F20-2",
            ),
            NautobotInterface(
                id="60d880c7-8618-414e-b4b4-fb6ac448c992",
                name="iDRAC",
                type="A_25GBASE_X_SFP28",
                description="Dedicated iDRAC interface",
                mac_address="A8:3C:A5:35:43:86",
                status="Active",
                ip_address="10.46.96.156",
                neighbor_device_id="912d38b1-1194-444c-8e19-5f455e16082e",
                neighbor_device_name="f20-2-1d.iad3.rackspace.net",
                neighbor_interface_id="4d010e0f-3135-4769-8bb0-71ba905edf01",
                neighbor_interface_name="GigabitEthernet1/0/3",
                neighbor_chassis_mac="9C:54:16:F5:AE:27",
                neighbor_location_name="IAD3",
                neighbor_rack_name="F20-2",
            ),
        ],
    )
