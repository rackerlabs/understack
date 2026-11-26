from unittest.mock import Mock

import pytest
from ironic.common import exception
from oslo_config import fixture as config_fixture

from ironic_understack.conf import CONF
from ironic_understack.drivers import cisco_nxos_base
from ironic_understack.drivers.cisco_nxos_inspect import CiscoNxosInspect
from ironic_understack.utils import nxos_api


@pytest.fixture
def conf():
    fixture = config_fixture.Config(CONF)
    fixture.setUp()
    yield fixture
    fixture.cleanUp()


@pytest.fixture
def node():
    node = Mock()
    node.uuid = "node-uuid"
    node.driver_info = {
        "nxos_address": "192.0.2.20",
        "nxos_username": "svc",
        "nxos_password": "example-pw",
    }
    return node


@pytest.fixture
def nxos_client(mocker):
    return mocker.patch.object(nxos_api, "NxosClient")


def test_get_properties_lists_what_validate_reads():
    assert set(CiscoNxosInspect().get_properties()) == {
        "nxos_address",
        "nxos_username",
        "nxos_password",
        "nxos_verify_ca",
    }


@pytest.mark.parametrize("key", ["nxos_address", "nxos_username", "nxos_password"])
def test_validate_requires(conf, node, key):
    del node.driver_info[key]
    with pytest.raises(exception.MissingParameterValue, match=key):
        CiscoNxosInspect().validate(Mock(node=node))


def test_validate_accepts_credentials_from_config(conf, node):
    conf.config(username="cfg-svc", password="cfg-pw", group="cisco_nxos")  # noqa: S106
    node.driver_info = {"nxos_address": "192.0.2.20"}
    CiscoNxosInspect().validate(Mock(node=node))


def test_client_falls_back_to_config(conf, node, nxos_client):
    conf.config(
        username="cfg-svc",
        password="cfg-pw",  # noqa: S106
        verify_ca="/etc/ssl/switch-ca.pem",
        group="cisco_nxos",
    )
    node.driver_info = {"nxos_address": "192.0.2.20", "nxos_username": ""}

    assert cisco_nxos_base.client(node) is nxos_client.return_value

    nxos_client.assert_called_once_with(
        "192.0.2.20", "cfg-svc", "cfg-pw", verify="/etc/ssl/switch-ca.pem"
    )


def test_driver_info_overrides_config(conf, node, nxos_client):
    conf.config(
        username="cfg-svc",
        password="cfg-pw",  # noqa: S106
        verify_ca="True",
        group="cisco_nxos",
    )
    node.driver_info["nxos_verify_ca"] = False

    cisco_nxos_base.client(node)

    nxos_client.assert_called_once_with("192.0.2.20", "svc", "example-pw", verify=False)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, False),
        ("", False),
        (True, True),
        ("true", True),
        ("False", False),
        ("/etc/ssl/switch-ca.pem", "/etc/ssl/switch-ca.pem"),
    ],
)
def test_verify_ca(conf, node, value, expected):
    if value is not None:
        node.driver_info["nxos_verify_ca"] = value
    assert cisco_nxos_base._verify_ca(node) == expected


def test_invalid_verify_ca_fails_validation(conf, node):
    node.driver_info["nxos_verify_ca"] = 1
    with pytest.raises(exception.InvalidParameterValue):
        CiscoNxosInspect().validate(Mock(node=node))
