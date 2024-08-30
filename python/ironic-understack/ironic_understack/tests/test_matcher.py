import pytest
from ironic_understack.flavor_spec import FlavorSpec
from ironic_understack.machine import Machine
from ironic_understack.matcher import Matcher

@pytest.fixture
def sample_flavors():
    return [
        FlavorSpec(name="small", memory_gb=4, cpu_cores=2, cpu_models=["x86", "ARM"], drives=[20], devices=[]),
        FlavorSpec(name="medium", memory_gb=8, cpu_cores=4, cpu_models=["x86"], drives=[40], devices=[]),
        FlavorSpec(name="large", memory_gb=16, cpu_cores=8, cpu_models=["x86"], drives=[80], devices=[]),
    ]

@pytest.fixture
def matcher(sample_flavors):
    return Matcher(flavors=sample_flavors)

@pytest.fixture
def machine():
    return Machine(memory_mb=8192, cpu="x86", disk_gb=50)

def test_match(matcher, machine):
    # This machine should match the small and medium flavors
    results = matcher.match(machine)
    assert len(results) == 2
    assert results[0].name == "small"
    assert results[1].name == "medium"

def test_match_no_flavor(matcher):
    # A machine that does not meet any flavor specs
    machine = Machine(memory_mb=2048, cpu="x86", disk_gb=10)
    results = matcher.match(machine)
    assert len(results) == 0

def test_pick_best_flavor2(matcher, machine):
    # This machine should pick the medium flavor as the best
    best_flavor = matcher.pick_best_flavor(machine)
    assert best_flavor is not None
    assert best_flavor.name == "medium"

def test_pick_best_flavor_no_match(matcher):
    # A machine that does not meet any flavor specs
    machine = Machine(memory_mb=1024, cpu="ARM", disk_gb=10)
    best_flavor = matcher.pick_best_flavor(machine)
    assert best_flavor is None
