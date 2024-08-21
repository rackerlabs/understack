import pytest
from ironic_understack.flavor_spec import FlavorSpec
from ironic_understack.machine import Machine
from ironic_understack.matcher import Matcher


@pytest.fixture
def machines():
    return [
        # 1024 GB, exact CPU, medium
        Machine(
            memory_mb=1024000, cpu="AMD EPYC 9254 245-Core Processor", disk_gb=1000
        ),
        # 800 GB, non-matching CPU
        Machine(memory_mb=800000, cpu="Intel Xeon E5-2676 v3", disk_gb=500),
        # 200 GB, exact CPU, medium
        Machine(memory_mb=200000, cpu="AMD EPYC 9254 245-Core Processor", disk_gb=1500),
        # 300 GB, non-matching CPU
        Machine(memory_mb=300000, cpu="Intel Xeon E5-2676 v3", disk_gb=500),
        # 409 GB, exact CPU, large
        Machine(memory_mb=409600, cpu="AMD EPYC 9254 245-Core Processor", disk_gb=2000),
    ]


@pytest.fixture
def flavors():
    return [
        FlavorSpec(
            name="small",
            memory_gb=100,
            cpu_cores=13,
            cpu_models=["AMD EPYC 9254 245-Core Processor", "Pentium 60"],
            drives=[500, 500],
            devices=[],
        ),
        FlavorSpec(
            name="medium",
            memory_gb=200,
            cpu_cores=15,
            cpu_models=["AMD EPYC 9254 245-Core Processor", "Intel 80386DX"],
            drives=[1500, 1500],
            devices=[],
        ),
        FlavorSpec(
            name="large",
            memory_gb=400,
            cpu_cores=27,
            cpu_models=["AMD EPYC 9254 245-Core Processor"],
            drives=[1800, 1800],
            devices=[],
        ),
    ]


def test_exact_match(machines, flavors):
    matcher = Matcher(machines, flavors)
    results = matcher.match()

    # Check for the 'small' flavor
    small_eligible_machines = results["small"]
    assert (
        len(small_eligible_machines) == 3
    )  # All machines meet the small flavor specs exactly
    # But exact match should be listed first.
    assert small_eligible_machines[0].memory_gb == 1024
    assert small_eligible_machines[0].disk_gb == 1000
    assert small_eligible_machines[0].cpu == "AMD EPYC 9254 245-Core Processor"


def test_no_match_due_to_memory(machines):
    high_memory_flavor = FlavorSpec(
        name="high_memory",
        memory_gb=1500,
        cpu_cores=32,
        cpu_models=["AMD EPYC 9254 245-Core Processor"],
        drives=[1000],
        devices=[],
    )

    matcher = Matcher(machines, [high_memory_flavor])
    results = matcher.match()

    assert len(results["high_memory"]) == 0  # No machine has >= 1500 GB of memory


def test_no_match_due_to_disk(machines):
    high_disk_flavor = FlavorSpec(
        name="high_disk",
        memory_gb=400,
        cpu_cores=27,
        cpu_models=["AMD EPYC 9254 245-Core Processor"],
        drives=[3000],
        devices=[],
    )

    matcher = Matcher(machines, [high_disk_flavor])
    results = matcher.match()

    assert len(results["high_disk"]) == 0  # No machine has >= 3000 GB of disk


def test_partial_match(machines, flavors):
    matcher = Matcher(machines, flavors)
    results = matcher.match()

    medium_eligible_machines = results["medium"]
    # Two machines are good enough to be medium
    assert len(medium_eligible_machines) == 2
    # But we should select one with smaller memory
    best_machine = medium_eligible_machines[0]
    assert all(
        best_machine.memory_gb <= machine.memory_gb
        for machine in medium_eligible_machines
    )
    assert all(
        best_machine.disk_gb <= machine.disk_gb
        for machine in medium_eligible_machines
    )
    # ...so that machine:
    assert best_machine == machines[2]


def test_higher_memory_and_disk(machines, flavors):
    matcher = Matcher(machines, flavors)
    results = matcher.match()

    large_eligible_machines = results["large"]
    # Only one machine meets large flavor specs exactly
    assert len(large_eligible_machines) == 1
    best_machine = large_eligible_machines[0]
    assert best_machine.memory_gb == 409  # Memory matches exactly
    assert best_machine.disk_gb == 2000  # Disk matches exactly
    assert best_machine.cpu == "AMD EPYC 9254 245-Core Processor"


def test_cpu_mismatch(machines):
    different_cpu_flavor = FlavorSpec(
        name="different_cpu",
        memory_gb=100,
        cpu_cores=13,
        cpu_models=["Intel Xeon Gold 6258R"],
        drives=[500, 500],
        devices=[],
    )

    matcher = Matcher(machines, [different_cpu_flavor])
    results = matcher.match()

    assert len(results["different_cpu"]) == 0
