import json

import pytest
from pytest_mock import MockerFixture

from understack_workflows.bmc_disk import Disk

TESTED_DISK_PATH = "/redfish/v1/Systems/System.Embedded.1/Storage/RAID.SL.1-1/Drives/Disk.Bay.1:Enclosure.Internal.0-1:RAID.SL.1-1"  # noqa: E501


@pytest.fixture
def mock_disk_data():
    with open("tests/json_samples/bmc_chassis_info/bmc_disk.json") as f:
        return json.load(f)


@pytest.fixture
def mock_bmc(mock_disk_data, mocker: MockerFixture):
    mock_bmc = mocker.Mock()
    mock_bmc.redfish_request.return_value = mock_disk_data
    return mock_bmc


def test_disk_from_path(mock_bmc):
    disk = Disk.from_path(mock_bmc, TESTED_DISK_PATH)
    assert isinstance(disk, Disk)


def test_disk_repr(mock_bmc):
    disk = Disk.from_path(mock_bmc, TESTED_DISK_PATH)
    assert repr(disk) == disk.name


def test_disk_attributes(mock_bmc):
    disk = Disk.from_path(mock_bmc, TESTED_DISK_PATH)
    assert disk.media_type == "SSD"
    assert disk.model == "MTFDDAK480TDS"
    assert disk.name == "Solid State Disk 0:1:1"
    assert disk.health == "OK"
    assert disk.capacity_bytes == 479559942144


def test_disk_gb_conversion():
    disk = Disk(
        media_type="SSD",
        model="Irrelevant",
        name="TestDisk",
        health="OK",
        capacity_bytes=479559942144,
    )
    assert disk.capacity_gb == 480
