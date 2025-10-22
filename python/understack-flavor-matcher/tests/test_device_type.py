import pytest

from flavor_matcher.device_type import DeviceType


@pytest.fixture
def valid_device_type_yaml():
    return """
class: server
manufacturer: Dell
model: PowerEdge R7615
u_height: 2
is_full_depth: true

interfaces:
  - name: iDRAC
    type: 1000base-t
    mgmt_only: true

resource_class:
  - name: m1.small
    cpu:
      cores: 16
      model: AMD EPYC 9124
    memory:
      size: 128
    drives:
      - size: 480
      - size: 480
    nic_count: 2

  - name: m1.medium
    cpu:
      cores: 32
      model: AMD EPYC 9334
    memory:
      size: 256
    drives:
      - size: 960
      - size: 960
    nic_count: 2
"""


def test_device_type_from_yaml(valid_device_type_yaml):
    device_type = DeviceType.from_yaml(valid_device_type_yaml)

    assert device_type.class_ == "server"
    assert device_type.manufacturer == "Dell"
    assert device_type.model == "PowerEdge R7615"
    assert device_type.u_height == 2
    assert device_type.is_full_depth is True

    # Check interfaces
    assert device_type.interfaces is not None
    assert len(device_type.interfaces) == 1
    assert device_type.interfaces[0].name == "iDRAC"
    assert device_type.interfaces[0].type == "1000base-t"
    assert device_type.interfaces[0].mgmt_only is True

    # Check resource classes
    assert len(device_type.resource_class) == 2

    # Check first resource class
    rc1 = device_type.resource_class[0]
    assert rc1.name == "m1.small"
    assert rc1.cpu.cores == 16
    assert rc1.cpu.model == "AMD EPYC 9124"
    assert rc1.memory.size == 128
    assert len(rc1.drives) == 2
    assert rc1.drives[0].size == 480
    assert rc1.drives[1].size == 480
    assert rc1.nic_count == 2

    # Check second resource class
    rc2 = device_type.resource_class[1]
    assert rc2.name == "m1.medium"
    assert rc2.cpu.cores == 32
    assert rc2.cpu.model == "AMD EPYC 9334"
    assert rc2.memory.size == 256


def test_get_resource_class(valid_device_type_yaml):
    device_type = DeviceType.from_yaml(valid_device_type_yaml)

    rc = device_type.get_resource_class("m1.small")
    assert rc is not None
    assert rc.name == "m1.small"
    assert rc.cpu.cores == 16

    rc = device_type.get_resource_class("m1.medium")
    assert rc is not None
    assert rc.name == "m1.medium"
    assert rc.cpu.cores == 32

    rc = device_type.get_resource_class("nonexistent")
    assert rc is None


def test_device_type_from_directory(tmp_path):
    # Create test files
    yaml_content = """
class: server
manufacturer: Dell
model: TestModel
u_height: 1
is_full_depth: false
resource_class:
  - name: test.small
    cpu:
      cores: 4
      model: Test CPU
    memory:
      size: 8
    drives:
      - size: 100
    nic_count: 1
"""
    test_file = tmp_path / "test-device.yaml"
    test_file.write_text(yaml_content)

    device_types = DeviceType.from_directory(tmp_path)
    assert len(device_types) == 1
    assert device_types[0].model == "TestModel"
    assert device_types[0].resource_class[0].name == "test.small"


def test_device_type_minimal_yaml():
    """Test with minimal required fields only."""
    minimal_yaml = """
class: server
manufacturer: Dell
model: TestModel
u_height: 1
is_full_depth: true
"""
    device_type = DeviceType.from_yaml(minimal_yaml)
    assert device_type.class_ == "server"
    assert device_type.manufacturer == "Dell"
    assert device_type.model == "TestModel"
    assert device_type.resource_class == []
    assert device_type.interfaces is None
    assert device_type.power_ports is None
