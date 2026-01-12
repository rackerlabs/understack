import json

import pytest
from pytest_mock import MockerFixture

from understack_workflows.bmc_disk import Disk

DELL_TEST_DISK_PATH = "/redfish/v1/Systems/System.Embedded.1/Storage/RAID.SL.1-1/Drives/Disk.Bay.1:Enclosure.Internal.0-1:RAID.SL.1-1"  # noqa: E501
HP_TEST_DISK_PATH = (
    "/redfish/v1/Systems/1/SmartStorage/ArrayControllers/3/DiskDrives/4/"
)


@pytest.fixture
def mock_dell_disk_data():
    with open("tests/json_samples/bmc_chassis_info/r7615_bmc_disk.json") as f:
        return json.load(f)


@pytest.fixture
def mock_hp_disk_data():
    with open("tests/json_samples/bmc_chassis_info/dl380_bmc_disk.json") as f:
        return json.load(f)


@pytest.fixture
def mock_dell_bmc(mock_dell_disk_data, mocker: MockerFixture):
    mock_bmc = mocker.Mock()
    mock_bmc.get_manufacturer.return_value = "dell inc."
    mock_bmc.redfish_request.return_value = mock_dell_disk_data
    return mock_bmc


@pytest.fixture
def mock_hp_bmc(mock_hp_disk_data, mocker: MockerFixture):
    mock_bmc = mocker.Mock()
    mock_bmc.get_manufacturer.return_value = "hpe"
    mock_bmc.redfish_request.return_value = mock_hp_disk_data
    return mock_bmc


def test_dell_disk_from_path(mock_dell_bmc):
    disk = Disk.from_path(mock_dell_bmc, DELL_TEST_DISK_PATH)
    assert isinstance(disk, Disk)


def test_dell_disk_repr(mock_dell_bmc):
    disk = Disk.from_path(mock_dell_bmc, DELL_TEST_DISK_PATH)
    assert repr(disk) == disk.name


def test_dell_disk_attributes(mock_dell_bmc):
    disk = Disk.from_path(mock_dell_bmc, DELL_TEST_DISK_PATH)
    assert disk.media_type == "SSD"
    assert disk.model == "MTFDDAK480TDS"
    assert disk.name == "Solid State Disk 0:1:1"
    assert disk.health == "OK"
    assert disk.capacity_bytes == 479559942144


def test_hp_disk_from_path(mock_hp_bmc):
    disk = Disk.from_path(mock_hp_bmc, HP_TEST_DISK_PATH)
    assert isinstance(disk, Disk)


def test_hp_disk_repr(mock_hp_bmc):
    disk = Disk.from_path(mock_hp_bmc, HP_TEST_DISK_PATH)
    assert repr(disk) == disk.name


def test_hp_disk_attributes(mock_hp_bmc):
    disk = Disk.from_path(mock_hp_bmc, HP_TEST_DISK_PATH)
    assert disk.media_type == "HDD"
    assert disk.model == "EH0600JEDHE"
    assert disk.name == "1I:1:1"
    assert disk.health == "OK"
    assert disk.capacity_bytes == 600000000000


def test_disk_gb_conversion():
    disk = Disk(
        media_type="SSD",
        model="Irrelevant",
        name="TestDisk",
        health="OK",
        capacity_bytes=479559942144,
    )
    assert disk.capacity_gb == 480
