from unittest.mock import mock_open, patch

import pytest
from flavor_matcher.flavor_spec import FlavorSpec
from flavor_matcher.machine import Machine


@pytest.fixture
def valid_yaml():
    return """
---
name: gp2.ultramedium
manufacturer: Dell
model: PowerEdge R7615
memory_gb: 7777
cpu_cores: 245
cpu_model: AMD EPYC 9254 245-Core Processor
drives:
    - 960
    - 960
"""


@pytest.fixture
def invalid_yaml():
    return """
---
name: gp2.ultramedium
x: abcd
malformed_field: 123: invalid
"""


@pytest.fixture
def yaml_directory(tmp_path, valid_yaml, invalid_yaml):
    valid_file = tmp_path / "valid.yaml"
    invalid_file = tmp_path / "invalid.yaml"

    valid_file.write_text(valid_yaml)
    invalid_file.write_text(invalid_yaml)

    return tmp_path


def test_from_yaml(valid_yaml):
    spec = FlavorSpec.from_yaml(valid_yaml)
    assert spec.name == "gp2.ultramedium"
    assert spec.manufacturer == "Dell"
    assert spec.model == "PowerEdge R7615"
    assert spec.memory_gb == 7777
    assert spec.cpu_cores == 245
    assert spec.cpu_model == "AMD EPYC 9254 245-Core Processor"
    assert spec.drives == [960, 960]


def test_from_yaml_invalid(invalid_yaml):
    with pytest.raises(Exception):
        FlavorSpec.from_yaml(invalid_yaml)


@patch("os.walk")
@patch("builtins.open", new_callable=mock_open)
def test_from_directory(mocked_open, mock_walk, valid_yaml, invalid_yaml):
    mock_walk.return_value = [
        ("/etc/flavors", [], ["valid.yaml", "invalid.yaml"]),
    ]
    mock_file_handles = [
        mock_open(read_data=valid_yaml).return_value,
        mock_open(read_data=invalid_yaml).return_value,
    ]

    mocked_open.side_effect = mock_file_handles

    specs = FlavorSpec.from_directory("/etc/flavors/")

    assert len(specs) == 1
    assert specs[0].name == "gp2.ultramedium"
    assert specs[0].memory_gb == 7777
    assert specs[0].cpu_cores == 245


def test_from_directory_with_real_files(yaml_directory):
    specs = FlavorSpec.from_directory(str(yaml_directory))

    assert len(specs) == 1
    assert specs[0].name == "gp2.ultramedium"
    assert specs[0].memory_gb == 7777
    assert specs[0].cpu_cores == 245


def test_empty_directory(tmp_path):
    specs = FlavorSpec.from_directory(str(tmp_path))
    assert len(specs) == 0


@pytest.fixture
def machines():
    return [
        # 1024 GB, exact CPU, medium
        Machine(
            memory_mb=102400,
            cpu="AMD EPYC 9254 245-Core Processor",
            disk_gb=1000,
            model="Dell XPS1319",
        ),
        # 800 GB, non-matching CPU
        Machine(
            memory_mb=800000,
            cpu="Intel Xeon E5-2676 v3",
            disk_gb=500,
            model="Dell XPS1319",
        ),
        # 200 GB, exact CPU, medium
        Machine(
            memory_mb=200000,
            cpu="AMD EPYC 9254 245-Core Processor",
            disk_gb=150,
            model="Dell XPS1319",
        ),
        # 300 GB, non-matching CPU
        Machine(
            memory_mb=300000,
            cpu="Intel Xeon E5-2676 v3",
            disk_gb=500,
            model="Dell XPS1319",
        ),
        # 409 GB, exact CPU, large
        Machine(
            memory_mb=409600,
            cpu="AMD EPYC 9254 245-Core Processor",
            disk_gb=2000,
            model="Dell XPS1319",
        ),
    ]


@pytest.fixture
def flavors():
    return [
        FlavorSpec(
            name="small",
            manufacturer="Dell",
            model="Dell XPS1319",
            memory_gb=100,
            cpu_cores=13,
            cpu_model="AMD EPYC 9254 245-Core Processor",
            drives=[500, 500],
            pci=[],
        ),
        FlavorSpec(
            name="medium",
            manufacturer="Dell",
            model="Fake Machine",
            memory_gb=200,
            cpu_cores=15,
            cpu_model="AMD EPYC 9254 245-Core Processor",
            drives=[1500, 1500],
            pci=[],
        ),
        FlavorSpec(
            name="large",
            manufacturer="Dell",
            model="Dell XPS1319",
            memory_gb=400,
            cpu_cores=27,
            cpu_model="AMD EPYC 9254 245-Core Processor",
            drives=[1800, 1800],
            pci=[],
        ),
    ]


def test_exact_match(flavors):
    machine = Machine(
        memory_mb=102400,
        cpu="AMD EPYC 9254 245-Core Processor",
        disk_gb=500,
        model="Dell XPS1319",
    )
    assert flavors[0].score_machine(machine) == 100
    assert flavors[1].score_machine(machine) == 0


def test_wrong_model_non_match(flavors):
    machine = Machine(
        memory_mb=102400,
        cpu="AMD EPYC 9254 245-Core Processor",
        disk_gb=500,
        model="Some other model",
    )
    for flavor in flavors:
        assert flavor.score_machine(machine) == 0


def test_memory_too_small(flavors):
    machine = Machine(
        memory_mb=51200,
        cpu="AMD EPYC 9254 245-Core Processor",
        disk_gb=500,
        model="Dell XPS1319",
    )
    for flavor in flavors:
        assert flavor.score_machine(machine) == 0


def test_disk_too_small(flavors):
    machine = Machine(
        memory_mb=204800,
        cpu="AMD EPYC 9254 245-Core Processor",
        disk_gb=100,
        model="Dell XPS1319",
    )
    assert all(flavor.score_machine(machine) == 0 for flavor in flavors)


def test_cpu_model_not_matching(flavors):
    machine = Machine(
        memory_mb=102400,
        cpu="Non-Existent CPU Model",
        disk_gb=500,
        model="Dell XPS1319",
    )
    assert all(flavor.score_machine(machine) == 0 for flavor in flavors)


def test_memory_match_but_more_disk(flavors):
    machine = Machine(
        memory_mb=102400,
        cpu="AMD EPYC 9254 245-Core Processor",
        disk_gb=1000,
        model="Dell XPS1319",
    )
    assert flavors[0].score_machine(machine) > 0


def test_disk_match_but_more_memory(flavors):
    machine = Machine(
        memory_mb=204800,
        cpu="AMD EPYC 9254 245-Core Processor",
        disk_gb=500,
        model="Dell XPS1319",
    )

    assert flavors[0].score_machine(machine) > 0
    assert flavors[1].score_machine(machine) == 0
    assert flavors[2].score_machine(machine) == 0


# Edge cases
def test_memory_slightly_less(flavors):
    # Machine with slightly less memory than required by the smallest flavor
    machine = Machine(
        memory_mb=102300,
        cpu="AMD EPYC 9254 245-Core Processor",
        disk_gb=500,
        model="Dell XPS1319",
    )
    # Should not match because memory is slightly less
    assert all(flavor.score_machine(machine) == 0 for flavor in flavors)


def test_disk_slightly_less(flavors):
    # Machine with slightly less disk space than required by the smallest flavor
    machine = Machine(
        memory_mb=102400,
        cpu="AMD EPYC 9254 245-Core Processor",
        disk_gb=499,
        model="Dell XPS1319",
    )
    # Should not match because disk space is slightly less
    assert all(flavor.score_machine(machine) == 0 for flavor in flavors)


def test_memory_exact_disk_slightly_more(flavors):
    # Machine with exact memory but slightly more disk space than required
    machine = Machine(
        memory_mb=102400,
        cpu="AMD EPYC 9254 245-Core Processor",
        disk_gb=501,
        model="Dell XPS1319",
    )
    assert flavors[0].score_machine(machine) > 0
    assert flavors[1].score_machine(machine) == 0
    assert flavors[2].score_machine(machine) == 0


def test_disk_exact_memory_slightly_more(flavors):
    # Machine with exact disk space but slightly more memory than required
    machine = Machine(
        memory_mb=102500,
        cpu="AMD EPYC 9254 245-Core Processor",
        disk_gb=500,
        model="Dell XPS1319",
    )
    assert flavors[0].score_machine(machine) > 0
    assert flavors[1].score_machine(machine) == 0
    assert flavors[2].score_machine(machine) == 0


def test_cpu_model_not_exact_but_memory_and_disk_match(flavors):
    # Machine with exact memory and disk space but CPU model is close but not exact
    machine = Machine(
        memory_mb=102400,
        cpu="AMD EPYC 9254 245-Core Processor v2",
        disk_gb=500,
        model="Dell XPS1319",
    )
    # Should not match because CPU model is not exactly listed
    assert all(flavor.score_machine(machine) == 0 for flavor in flavors)


def test_large_flavor_memory_slightly_less_disk_exact(flavors):
    # Machine with slightly less memory than required for the medium flavor, exact disk space
    machine = Machine(
        memory_mb=204600, cpu="Intel 80386DX", disk_gb=1800, model="Dell XPS1319"
    )
    # Should not match because memory is slightly less than required
    assert all(flavor.score_machine(machine) == 0 for flavor in flavors)
