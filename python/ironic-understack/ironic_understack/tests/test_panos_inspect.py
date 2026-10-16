from unittest.mock import Mock

import pytest
import requests
from ironic.common import exception
from ironic.common import states

from ironic_understack.drivers import panos_inspect
from ironic_understack.drivers.panos_inspect import PanosInspect
from ironic_understack.utils import panos_api

SYSTEM = {"model": "PA-1410", "serial": "000000000001", "sw-version": "11.0.0"}


@pytest.fixture
def task():
    task = Mock()
    task.node.uuid = "node-uuid"
    task.node.driver_info = {"management_ip": "192.0.2.10"}
    task.node.properties = {}
    task.node.extra = {}
    return task


@pytest.fixture
def client(mocker):
    client = Mock()
    client.login.return_value = "standard"
    client.system_info.return_value = dict(SYSTEM)
    mocker.patch.object(panos_api, "PanosClient", return_value=client)
    return client


def test_get_properties_matches_what_validate_reads():
    assert set(PanosInspect().get_properties()) == {"management_ip"}


def test_validate_requires_management_ip(task):
    task.node.driver_info = {}
    with pytest.raises(exception.MissingParameterValue):
        PanosInspect().validate(task)


def test_validate_success(task):
    PanosInspect().validate(task)


def test_inspect_records_system_info(task, client):
    assert PanosInspect().inspect_hardware(task) == states.MANAGEABLE

    panos_api.PanosClient.assert_called_once_with("192.0.2.10")
    assert task.node.properties == {"model": "PA-1410", "firmware_version": "11.0.0"}
    assert task.node.extra == {"serial": "000000000001"}
    task.node.save.assert_called_once()


def test_inspect_keeps_enrolled_model_and_serial(task, client):
    # enroll-fw sets these from Nautobot; inspection does not overwrite them.
    task.node.properties = {"model": "PA-1410-NB", "vendor": "Palo Alto"}
    task.node.extra = {"serial": "nautobot-serial", "mate_serial": "mate"}

    PanosInspect().inspect_hardware(task)

    assert task.node.properties == {
        "model": "PA-1410-NB",
        "vendor": "Palo Alto",
        "firmware_version": "11.0.0",
    }
    assert task.node.extra == {"serial": "nautobot-serial", "mate_serial": "mate"}


@pytest.mark.parametrize(
    "error",
    [panos_api.PanosApiError("rejected"), requests.ConnectionError("unreachable")],
)
def test_inspect_failure(task, client, error):
    client.login.side_effect = error

    with pytest.raises(exception.HardwareInspectionFailure, match=r"192\.0\.2\.10"):
        PanosInspect().inspect_hardware(task)
    task.node.save.assert_not_called()


def test_apply_system_info_ignores_empty_fields(task):
    panos_inspect._apply_system_info(task.node, {"model": "", "serial": ""})
    assert task.node.properties == {}
    assert task.node.extra == {}
