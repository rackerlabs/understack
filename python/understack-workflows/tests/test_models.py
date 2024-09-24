from understack_workflows.models import NIC
from understack_workflows.models import Systeminfo


def test_nic():
    value = "test"
    a = NIC(name=value, location=value, interfaces=[], model=value)

    assert a.name == value
    assert a.location == value
    assert a.model == value


def test_system_info():
    value = "test"
    sys_info = Systeminfo(asset_tag=value, serial_number=value, platform=value)

    assert sys_info.asset_tag == value
    assert sys_info.serial_number == value
    assert sys_info.platform == value
