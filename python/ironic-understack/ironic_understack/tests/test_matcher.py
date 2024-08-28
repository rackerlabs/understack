import pytest
from ironic_understack.flavor_spec import FlavorSpec
from ironic_understack.machine import Machine
from ironic_understack.matcher import Matcher


@pytest.fixture
def machines():
    return [
        # 1024 GB, exact CPU, medium
        Machine(
            memory_mb=102400, cpu="AMD EPYC 9254 245-Core Processor", disk_gb=1000
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

def test_exact_match(flavors):
    machine = Machine(memory_mb=102400, cpu="AMD EPYC 9254 245-Core Processor", disk_gb=500)
    matcher = Matcher(flavors)
    matched_flavors = matcher.match(machine)
    assert len(matched_flavors) == 1
    assert matched_flavors[0].name == "small"


def test_memory_too_small(flavors):
    machine = Machine(memory_mb=51200, cpu="AMD EPYC 9254 245-Core Processor", disk_gb=500)
    matcher = Matcher(flavors)
    matched_flavors = matcher.match(machine)
    assert len(matched_flavors) == 0


def test_disk_too_small(flavors):
    machine = Machine(memory_mb=204800, cpu="AMD EPYC 9254 245-Core Processor", disk_gb=100)
    matcher = Matcher(flavors)
    matched_flavors = matcher.match(machine)
    assert len(matched_flavors) == 0


def test_cpu_model_not_matching(flavors):
    machine = Machine(memory_mb=102400, cpu="Non-Existent CPU Model", disk_gb=500)
    matcher = Matcher(flavors)
    matched_flavors = matcher.match(machine)
    assert len(matched_flavors) == 0


def test_memory_match_but_more_disk(flavors):
    machine = Machine(memory_mb=102400, cpu="AMD EPYC 9254 245-Core Processor", disk_gb=1000)
    matcher = Matcher(flavors)
    matched_flavors = matcher.match(machine)
    assert len(matched_flavors) == 1
    assert matched_flavors[0].name == "small"


def test_disk_match_but_more_memory(flavors):
    machine = Machine(memory_mb=204800, cpu="AMD EPYC 9254 245-Core Processor", disk_gb=500)
    matcher = Matcher(flavors)
    matched_flavors = matcher.match(machine)
    assert len(matched_flavors) == 1
    assert matched_flavors[0].name == "small"


def test_pick_best_flavor(flavors):
    machine = Machine(memory_mb=204800, cpu="AMD EPYC 9254 245-Core Processor", disk_gb=1500)
    matcher = Matcher(flavors)
    best_flavor = matcher.pick_best_flavor(machine)
    assert best_flavor is not None
    assert best_flavor.name == "medium"


def test_no_matching_flavor(flavors):
    machine = Machine(memory_mb=51200, cpu="Non-Existent CPU Model", disk_gb=250)
    matcher = Matcher(flavors)
    best_flavor = matcher.pick_best_flavor(machine)
    assert best_flavor is None


def test_multiple_flavors_available(flavors):
    machine = Machine(memory_mb=204800, cpu="AMD EPYC 9254 245-Core Processor", disk_gb=2000)
    matcher = Matcher(flavors)
    matched_flavors = matcher.match(machine)
    assert len(matched_flavors) == 2  # small and medium should be available
    best_flavor = matcher.pick_best_flavor(machine)
    assert best_flavor.name == "medium"  # medium has more memory, so it should be selected


# Edge cases
def test_memory_slightly_less(flavors):
    # Machine with slightly less memory than required by the smallest flavor
    machine = Machine(memory_mb=102300, cpu="AMD EPYC 9254 245-Core Processor", disk_gb=500)
    matcher = Matcher(flavors)
    matched_flavors = matcher.match(machine)
    assert len(matched_flavors) == 0  # Should not match because memory is slightly less


def test_disk_slightly_less(flavors):
    # Machine with slightly less disk space than required by the smallest flavor
    machine = Machine(memory_mb=102400, cpu="AMD EPYC 9254 245-Core Processor", disk_gb=499)
    matcher = Matcher(flavors)
    matched_flavors = matcher.match(machine)
    assert len(matched_flavors) == 0  # Should not match because disk space is slightly less


def test_memory_exact_disk_slightly_more(flavors):
    # Machine with exact memory but slightly more disk space than required
    machine = Machine(memory_mb=102400, cpu="AMD EPYC 9254 245-Core Processor", disk_gb=501)
    matcher = Matcher(flavors)
    matched_flavors = matcher.match(machine)
    assert len(matched_flavors) == 1
    assert matched_flavors[0].name == "small"  # Should match but with a lower score due to extra disk space


def test_disk_exact_memory_slightly_more(flavors):
    # Machine with exact disk space but slightly more memory than required
    machine = Machine(memory_mb=102500, cpu="AMD EPYC 9254 245-Core Processor", disk_gb=500)
    matcher = Matcher(flavors)
    matched_flavors = matcher.match(machine)
    assert len(matched_flavors) == 1
    assert matched_flavors[0].name == "small"  # Should match but with a lower score due to extra memory


def test_cpu_model_not_exact_but_memory_and_disk_match(flavors):
    # Machine with exact memory and disk space but CPU model is close but not exact
    machine = Machine(memory_mb=102400, cpu="AMD EPYC 9254 245-Core Processor v2", disk_gb=500)
    matcher = Matcher(flavors)
    matched_flavors = matcher.match(machine)
    assert len(matched_flavors) == 0  # Should not match because CPU model is not exactly listed


def test_large_flavor_memory_slightly_less_disk_exact(flavors):
    # Machine with slightly less memory than required for the medium flavor, exact disk space
    machine = Machine(memory_mb=204600, cpu="Intel 80386DX", disk_gb=1800)
    matcher = Matcher(flavors)
    matched_flavors = matcher.match(machine)
    assert len(matched_flavors) == 0  # Should not match because memory is slightly less than required
