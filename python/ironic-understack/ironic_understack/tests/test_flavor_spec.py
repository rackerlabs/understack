from unittest.mock import mock_open, patch

import pytest
from ironic_understack.flavor_spec import FlavorSpec


@pytest.fixture
def valid_yaml():
    return """
---
name: gp2.ultramedium
memory_gb: 7777
cpu_cores: 245
cpu_models:
    - AMD EPYC 9254 245-Core Processor
drives:
    - 960
    - 960
devices:
    - PowerEdge R7515
    - PowerEdge R7615
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
    assert spec.memory_gb == 7777
    assert spec.cpu_cores == 245
    assert spec.cpu_models == ["AMD EPYC 9254 245-Core Processor"]
    assert spec.drives == [960, 960]
    assert spec.devices == ["PowerEdge R7515", "PowerEdge R7615"]


def test_from_yaml_invalid(invalid_yaml):
    with pytest.raises(Exception):
        FlavorSpec.from_yaml(invalid_yaml)


@patch("os.listdir")
@patch("builtins.open", new_callable=mock_open)
def test_from_directory(mocked_open, mock_listdir, valid_yaml, invalid_yaml):
    mock_listdir.return_value = ["valid.yaml", "invalid.yaml"]
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
