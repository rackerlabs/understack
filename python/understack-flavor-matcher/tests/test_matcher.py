import pytest

from flavor_matcher.device_type import CpuSpec
from flavor_matcher.device_type import DeviceType
from flavor_matcher.device_type import DriveSpec
from flavor_matcher.device_type import MemorySpec
from flavor_matcher.device_type import ResourceClass
from flavor_matcher.machine import Machine
from flavor_matcher.matcher import Matcher


@pytest.fixture
def device_types():
    """Create sample device types for testing."""
    # Dell PowerEdge R7615 with multiple resource classes
    dell_r7615 = DeviceType(
        class_="server",
        manufacturer="Dell",
        model="PowerEdge R7615",
        u_height=2,
        is_full_depth=True,
        resource_class=[
            ResourceClass(
                name="m1.small",
                cpu=CpuSpec(cores=16, model="AMD EPYC 9124"),
                memory=MemorySpec(size=131072),
                drives=[DriveSpec(size=480), DriveSpec(size=480)],
                nic_count=2,
            ),
            ResourceClass(
                name="m1.medium",
                cpu=CpuSpec(cores=32, model="AMD EPYC 9334"),
                memory=MemorySpec(size=262144),
                drives=[DriveSpec(size=960), DriveSpec(size=960)],
                nic_count=2,
            ),
            ResourceClass(
                name="m1.large",
                cpu=CpuSpec(cores=64, model="AMD EPYC 9554"),
                memory=MemorySpec(size=524288),
                drives=[DriveSpec(size=1920), DriveSpec(size=1920)],
                nic_count=4,
            ),
        ],
    )

    return [dell_r7615]


@pytest.fixture
def matcher(device_types):
    """Create a matcher with test data."""
    return Matcher(device_types=device_types)


def test_match_exact_machine(matcher):
    """Test matching a machine that exactly matches m1.small resource class."""
    machine = Machine(
        memory_mb=131072,  # 128 GB
        cpu="AMD EPYC 9124",
        cpu_cores=16,
        disk_gb=480,
        manufacturer="Dell",
        model="PowerEdge R7615",
    )

    result = matcher.match(machine)
    assert result is not None
    device_type, resource_class = result
    assert resource_class.name == "m1.small"
    assert device_type.manufacturer == "Dell"
    assert device_type.model == "PowerEdge R7615"


def test_match_machine_small(matcher):
    """Test that machine matches the m1.small resource class."""
    machine = Machine(
        memory_mb=131072,  # 128 GB
        cpu="AMD EPYC 9124",
        cpu_cores=16,
        disk_gb=480,
        manufacturer="Dell",
        model="PowerEdge R7615",
    )

    result = matcher.match(machine)
    assert result is not None
    _, resource_class = result
    assert resource_class.name == "m1.small"


def test_match_machine_verifies_specs(matcher):
    """Test that machine matches based on hardware specs."""
    machine = Machine(
        memory_mb=131072,  # 128 GB
        cpu="AMD EPYC 9124",
        cpu_cores=16,
        disk_gb=480,
        manufacturer="Dell",
        model="PowerEdge R7615",
    )

    result = matcher.match(machine)
    assert result is not None
    _, resource_class = result
    assert resource_class.name == "m1.small"
    assert resource_class.cpu.cores == 16
    assert resource_class.memory.size == 131072


def test_match_medium_machine(matcher):
    """Test matching a machine to m1.medium resource class."""
    machine = Machine(
        memory_mb=262144,  # 256 GB
        cpu="AMD EPYC 9334",
        cpu_cores=32,
        disk_gb=960,
        manufacturer="Dell",
        model="PowerEdge R7615",
    )

    result = matcher.match(machine)
    assert result is not None
    _, resource_class = result
    assert resource_class.name == "m1.medium"


def test_match_medium_machine_with_specs(matcher):
    """Test matching a medium machine and verify its specs."""
    machine = Machine(
        memory_mb=262144,  # 256 GB
        cpu="AMD EPYC 9334",
        cpu_cores=32,
        disk_gb=960,
        manufacturer="Dell",
        model="PowerEdge R7615",
    )

    result = matcher.match(machine)
    assert result is not None
    _, resource_class = result
    assert resource_class.name == "m1.medium"
    assert resource_class.cpu.cores == 32
    assert resource_class.memory.size == 262144


def test_no_match_wrong_manufacturer(matcher):
    """Test that wrong manufacturer doesn't match."""
    machine = Machine(
        memory_mb=131072,  # 128 GB
        cpu="AMD EPYC 9124",
        cpu_cores=16,
        disk_gb=480,
        manufacturer="HP",  # Wrong manufacturer
        model="PowerEdge R7615",
    )

    result = matcher.match(machine)
    assert result is None


def test_no_match_wrong_model(matcher):
    """Test that wrong model doesn't match."""
    machine = Machine(
        memory_mb=131072,  # 128 GB
        cpu="AMD EPYC 9124",
        cpu_cores=16,
        disk_gb=480,
        manufacturer="Dell",
        model="PowerEdge R7525",  # Wrong model
    )

    result = matcher.match(machine)
    assert result is None


def test_no_match_wrong_cpu_model(matcher):
    """Test that wrong CPU model doesn't match."""
    machine = Machine(
        memory_mb=131072,  # 128 GB
        cpu="Intel Xeon",  # Wrong CPU
        cpu_cores=16,
        disk_gb=480,
        manufacturer="Dell",
        model="PowerEdge R7615",
    )

    result = matcher.match(machine)
    assert result is None


def test_no_match_wrong_memory(matcher):
    """Test that wrong memory size doesn't match."""
    machine = Machine(
        memory_mb=65536,  # 64 GB - wrong size
        cpu="AMD EPYC 9124",
        cpu_cores=16,
        disk_gb=480,
        manufacturer="Dell",
        model="PowerEdge R7615",
    )

    result = matcher.match(machine)
    assert result is None


def test_no_match_insufficient_disk(matcher):
    """Test that insufficient disk space doesn't match."""
    machine = Machine(
        memory_mb=131072,  # 128 GB
        cpu="AMD EPYC 9124",
        cpu_cores=16,
        disk_gb=200,  # Too small
        manufacturer="Dell",
        model="PowerEdge R7615",
    )

    result = matcher.match(machine)
    assert result is None


def test_match_empty_device_types():
    """Test matcher with no device types."""
    matcher = Matcher(device_types=[])
    machine = Machine(
        memory_mb=131072,
        cpu="AMD EPYC 9124",
        cpu_cores=16,
        disk_gb=480,
        manufacturer="Dell",
        model="PowerEdge R7615",
    )

    result = matcher.match(machine)
    assert result is None
