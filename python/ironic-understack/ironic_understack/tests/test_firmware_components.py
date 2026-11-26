from unittest.mock import Mock

import pytest
from ironic import objects

from ironic_understack.utils import firmware_components

SETTING = {
    "component": "os",
    "current_version": "2.0",
    "vendor": "Example",
    "model": "M1",
    "serial_number": "S1",
}


@pytest.fixture
def task():
    task = Mock()
    task.node.id = 7
    return task


@pytest.fixture
def sync(mocker):
    objects.register_all()
    mocker.patch.object(objects, "FirmwareComponent")
    return mocker.patch.object(
        objects.FirmwareComponentList,
        "sync_firmware_components",
        return_value=([], [], []),
    )


def test_creates_new_components(task, sync):
    sync.return_value = ([SETTING], [], [])

    firmware_components.sync(task, [SETTING])

    sync.assert_called_once_with(task.context, 7, [SETTING])
    objects.FirmwareComponent.assert_called_once_with(
        task.context, node_id=7, **SETTING
    )
    objects.FirmwareComponent.return_value.create.assert_called_once()


def test_changed_version_is_recorded_as_flashed(task, sync):
    sync.return_value = ([], [SETTING], [])
    existing = Mock(current_version="1.0", last_version_flashed=None)
    objects.FirmwareComponent.get.return_value = existing

    firmware_components.sync(task, [SETTING])

    objects.FirmwareComponent.get.assert_called_once_with(
        task.context, node_id=7, name="os"
    )
    assert existing.current_version == "2.0"
    assert existing.last_version_flashed == "2.0"
    assert (existing.vendor, existing.model, existing.serial_number) == (
        "Example",
        "M1",
        "S1",
    )
    existing.save.assert_called_once()


def test_unchanged_version_keeps_last_flashed(task, sync):
    sync.return_value = ([], [SETTING], [])
    existing = Mock(current_version="2.0", last_version_flashed="1.5")
    objects.FirmwareComponent.get.return_value = existing

    firmware_components.sync(task, [SETTING])

    assert existing.last_version_flashed == "1.5"
    existing.save.assert_called_once()
