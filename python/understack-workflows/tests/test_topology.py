import json
import pathlib

from understack_workflows.topology import pxe_interface_name
from understack_workflows.topology import switch_connections


def read_json_samples(file_path):
    here = pathlib.Path(__file__).parent
    ref = here.joinpath(file_path)
    with ref.open("r") as f:
        return json.loads(f.read())


NAUTOBOT_DATA = read_json_samples("json_samples/nautobot_device_data.json")


def test_pxe_interface_name():
    assert pxe_interface_name(NAUTOBOT_DATA) == "NIC.Slot.1-2"


def test_switch_connections():
    assert switch_connections(NAUTOBOT_DATA) == {
        "NIC.Integrated.1-1": "f20-2-1.iad3.rackspace.net",
        "NIC.Integrated.1-2": "f20-2-2.iad3.rackspace.net",
        "NIC.Slot.1-2": "f20-2-1.iad3.rackspace.net",
        "NIC.Slot.1-1": "f20-2-2.iad3.rackspace.net",
        "iDRAC": "f20-2-1d.iad3.rackspace.net",
    }
