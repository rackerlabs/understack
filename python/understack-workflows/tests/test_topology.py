from understack_workflows.nautobot_device import NautobotDevice
from understack_workflows.nautobot_device import NautobotInterface
from understack_workflows.topology import pxe_interface_name
from understack_workflows.topology import switch_connections

NAUTOBOT_DATA = NautobotDevice(
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
            ip_address=None,
            neighbor_device_id="275ef491-2b27-4d1b-bd45-330bd6b7e0cf",
            neighbor_device_name="f20-2-1.iad3.rackspace.net",
            neighbor_interface_id="f9a5cc87-d10a-4827-99e8-48961fd1d773",
            neighbor_interface_name="2148cf50-f70e-42c9-9f68-8ce98d61498c",
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
            ip_address=None,
            neighbor_device_id="05f6715a-4dbe-4fd6-af20-1e73adb285c2",
            neighbor_device_name="f20-2-2.iad3.rackspace.net",
            neighbor_interface_id="2148cf50-f70e-42c9-9f68-8ce98d61498c",
            neighbor_interface_name="2148cf50-f70e-42c9-9f68-8ce98d61498c",
            neighbor_chassis_mac="9C:54:16:F5:AC:27",
            neighbor_location_name="IAD3",
            neighbor_rack_name="F20-2",
        ),
    ],
)


def test_pxe_interface_name():
    assert pxe_interface_name(NAUTOBOT_DATA) == "NIC.Integrated.1-1"


def test_switch_connections():
    assert switch_connections(NAUTOBOT_DATA) == {
        "NIC.Integrated.1-1": "f20-2-1.iad3.rackspace.net",
        "NIC.Integrated.1-2": "f20-2-2.iad3.rackspace.net",
    }
