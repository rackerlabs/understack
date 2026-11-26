from unittest.mock import MagicMock
from unittest.mock import Mock

import pytest
import requests
from ironic import objects
from ironic.common import exception

from ironic_understack.drivers import cisco_nxos_firmware
from ironic_understack.drivers.cisco_nxos_firmware import CiscoNxosFirmware
from ironic_understack.utils import nxos_api

VERSION = {
    "nxos_ver_str": "10.3(4a)",
    "bios_ver_str": "07.69",
    "chassis_id": "Nexus9000 C93180YC-FX Chassis",
    "proc_board_id": "FDO00000001",
}


@pytest.fixture
def task():
    task = Mock()
    task.node.id = 7
    task.node.uuid = "node-uuid"
    task.node.driver_info = {
        "nxos_address": "192.0.2.20",
        "nxos_username": "svc",
        "nxos_password": "example-pw",
    }
    return task


@pytest.fixture
def client(mocker):
    client = MagicMock()
    client.__enter__.return_value = client
    client.show_version.return_value = dict(VERSION)
    mocker.patch.object(nxos_api, "NxosClient", return_value=client)
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
    fw = CiscoNxosFirmware()
    assert {s["step"]: s["priority"] for s in fw.get_clean_steps(Mock())} == {
        "cache_firmware_components": 0
    }
    assert [s["step"] for s in fw.get_verify_steps(Mock())] == [
        "cache_firmware_components"
    ]


def test_components_from_show_version():
    # bios_ver_str is in the output but is not recorded.
    (nxos,) = cisco_nxos_firmware.components_from_show_version(VERSION)
    assert nxos == {
        "component": "nxos",
        "current_version": "10.3(4a)",
        "vendor": None,
        "model": None,
        "serial_number": None,
    }


def test_older_releases_report_the_system_version():
    assert cisco_nxos_firmware.nxos_version({"sys_ver_str": "7.0(3)I7(9)"}) == (
        "7.0(3)I7(9)"
    )


def test_update_is_unsupported(task):
    with pytest.raises(exception.UnsupportedDriverExtension):
        CiscoNxosFirmware().update(task, [])


def test_cache_creates_components(task, client, sync):
    sync.return_value = (
        cisco_nxos_firmware.components_from_show_version(VERSION),
        [],
        [],
    )

    CiscoNxosFirmware().cache_firmware_components(task)

    client.__exit__.assert_called_once()
    nxos_api.NxosClient.assert_called_once_with(
        "192.0.2.20", "svc", "example-pw", verify=False
    )
    created = [c.kwargs for c in objects.FirmwareComponent.call_args_list]
    assert [(c["component"], c["current_version"]) for c in created] == [
        ("nxos", "10.3(4a)"),
    ]


def test_cache_updates_changed_version(task, client, sync):
    new = cisco_nxos_firmware.components_from_show_version(VERSION)[0]
    sync.return_value = ([], [new], [])
    existing = Mock(current_version="10.2(5)")
    objects.FirmwareComponent.get.return_value = existing

    CiscoNxosFirmware().cache_firmware_components(task)

    assert existing.current_version == "10.3(4a)"
    assert existing.last_version_flashed == "10.3(4a)"
    existing.save.assert_called_once()


def test_nothing_reported_is_unsupported(task, client, sync):
    client.show_version.return_value = {}
    with pytest.raises(exception.UnsupportedDriverExtension):
        CiscoNxosFirmware().cache_firmware_components(task)
    sync.assert_not_called()


@pytest.mark.parametrize(
    "error",
    [nxos_api.NxosApiError("rejected"), requests.ConnectionError("unreachable")],
)
def test_cache_failure(task, client, sync, error):
    client.show_version.side_effect = error
    with pytest.raises(exception.IronicException, match=r"192\.0\.2\.20"):
        CiscoNxosFirmware().cache_firmware_components(task)
    sync.assert_not_called()
