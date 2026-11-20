from unittest.mock import Mock

import pytest
import requests
from ironic import objects
from ironic.common import exception

from ironic_understack.drivers import panos_firmware
from ironic_understack.drivers.panos_firmware import PanosFirmware
from ironic_understack.utils import panos_api

SYSTEM = {
    "model": "PA-1410",
    "serial": "000000000001",
    "sw-version": "11.0.0",
    "app-version": "8900-9000",
    "av-version": "0",
    "wildfire-version": "",
    "global-protect-client-package-version": "6.2.0",
}


@pytest.fixture
def task():
    task = Mock()
    task.node.id = 7
    task.node.uuid = "node-uuid"
    task.node.driver = "panos"
    task.node.driver_info = {"management_ip": "192.0.2.10"}
    return task


@pytest.fixture
def client(mocker):
    client = Mock()
    client.system_info.return_value = dict(SYSTEM)
    mocker.patch.object(panos_api, "PanosClient", return_value=client)
    return client


@pytest.fixture
def sync(mocker):
    objects.register_all()
    mocker.patch.object(objects, "FirmwareComponent")
    return mocker.patch.object(
        objects.FirmwareComponentList,
        "sync_firmware_components",
        return_value=([], [], []),
    )


def test_steps_are_registered():
    fw = PanosFirmware()
    assert {s["step"]: s["priority"] for s in fw.get_clean_steps(Mock())} == {
        "cache_firmware_components": 0
    }
    assert [s["step"] for s in fw.get_verify_steps(Mock())] == [
        "cache_firmware_components"
    ]
    assert [s["step"] for s in fw.get_service_steps(Mock())] == [
        "cache_firmware_components"
    ]


def test_validate_requires_management_ip(task):
    task.node.driver_info = {}
    with pytest.raises(exception.MissingParameterValue):
        PanosFirmware().validate(task)


def test_update_is_unsupported(task):
    with pytest.raises(exception.UnsupportedDriverExtension):
        PanosFirmware().update(task, [])


def test_components_skip_uninstalled_content():
    settings = panos_firmware._components_from_system_info(SYSTEM)
    assert {s["component"]: s["current_version"] for s in settings} == {
        "panos": "11.0.0",
        "app-content": "8900-9000",
        "globalprotect-client": "6.2.0",
    }
    panos = settings[0]
    assert panos["vendor"] == "Palo Alto Networks"
    assert panos["model"] == "PA-1410"
    assert panos["serial_number"] == "000000000001"


def test_cache_creates_new_components(task, client, sync, mocker):
    sync.return_value = (
        panos_firmware._components_from_system_info(SYSTEM),
        [],
        [],
    )

    PanosFirmware().cache_firmware_components(task)

    panos_api.PanosClient.assert_called_once_with("192.0.2.10")
    assert objects.FirmwareComponent.call_count == 3
    created = objects.FirmwareComponent.call_args_list[0].kwargs
    assert created["component"] == "panos"
    assert created["current_version"] == "11.0.0"


def test_cache_updates_changed_component(task, client, sync):
    new = panos_firmware._components_from_system_info(SYSTEM)[0]
    sync.return_value = ([], [new], [])
    existing = Mock(current_version="10.2.0")
    objects.FirmwareComponent.get.return_value = existing

    PanosFirmware().cache_firmware_components(task)

    assert existing.current_version == "11.0.0"
    assert existing.last_version_flashed == "11.0.0"
    existing.save.assert_called_once()


@pytest.mark.parametrize(
    "error",
    [panos_api.PanosApiError("rejected"), requests.ConnectionError("unreachable")],
)
def test_cache_failure(task, client, sync, error):
    client.login.side_effect = error
    with pytest.raises(exception.IronicException, match=r"192\.0\.2\.10"):
        PanosFirmware().cache_firmware_components(task)
    sync.assert_not_called()


def test_cache_with_no_components(task, client, sync):
    client.system_info.return_value = {"model": "PA-1410"}
    with pytest.raises(exception.UnsupportedDriverExtension):
        PanosFirmware().cache_firmware_components(task)
