import pytest

from flavor_matcher.flavor_spec import FlavorSpec
from flavor_matcher.machine import Machine
from flavor_matcher.matcher import Matcher


@pytest.fixture
def sample_flavors():
    return [
        FlavorSpec(
            name="small",
            manufacturer="Dell",
            model="Fake Machine",
            memory_gb=4,
            cpu_cores=2,
            cpu_model="x86",
            drives=[20],
            pci=[],
        ),
        FlavorSpec(
            name="medium",
            manufacturer="Dell",
            model="Fake Machine",
            memory_gb=8,
            cpu_cores=4,
            cpu_model="x86",
            drives=[40],
            pci=[],
        ),
        FlavorSpec(
            name="large",
            manufacturer="Dell",
            model="Fake Machine",
            memory_gb=16,
            cpu_cores=8,
            cpu_model="x86",
            drives=[80],
            pci=[],
        ),
    ]


@pytest.fixture
def matcher(sample_flavors):
    return Matcher(flavors=sample_flavors)


@pytest.fixture
def machine():
    return Machine(memory_mb=8192, cpu="x86", disk_gb=50, model="Fake Machine")


def test_match(matcher, machine):
    # This machine should match the small and medium flavors
    results = matcher.match(machine)
    assert len(results) == 2
    assert results[0].name == "small"
    assert results[1].name == "medium"


def test_match_no_flavor(matcher):
    # A machine that does not meet any flavor specs
    machine = Machine(memory_mb=2048, cpu="x86", disk_gb=10, model="SomeModel")
    results = matcher.match(machine)
    assert len(results) == 0


def test_pick_best_flavor2(matcher, machine):
    # This machine should pick the medium flavor as the best
    best_flavor = matcher.pick_best_flavor(machine)
    assert best_flavor is not None
    assert best_flavor.name == "medium"


def test_pick_best_flavor_no_match(matcher):
    # A machine that does not meet any flavor specs
    machine = Machine(memory_mb=1024, cpu="ARM", disk_gb=10, model="SomeModel")
    best_flavor = matcher.pick_best_flavor(machine)
    assert best_flavor is None
