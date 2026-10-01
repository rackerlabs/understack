"""Tests for network device credential loading."""

import pytest
from oslo_config import fixture as config_fixture

from ironic_understack.conf import CONF
from ironic_understack.utils import netdev_credentials as nc


@pytest.fixture
def conf():
    fixture = config_fixture.Config(CONF)
    fixture.setUp()
    yield fixture
    fixture.cleanUp()


def test_credentials_shape(conf):
    conf.config(standard_password="pan-pw", group="netdev_panos")  # noqa: S106
    conf.config(root_standard_password="f5-pw", group="netdev_f5")  # noqa: S106
    conf.config(
        service_account_a_username="svc-a",
        service_account_a_password="svc-pw",  # noqa: S106
        group="netdev_common",
    )

    assert nc.get_panos_credentials() == {
        "username": "admin",
        "standard_password": "pan-pw",
        "preconfig_password": None,
        "factory_password": "admin",
        "panorama_master_key": None,
    }
    assert nc.get_f5_credentials() == {
        "root": {
            "username": "root",
            "standard_password": "f5-pw",
            "preconfig_password": None,
        },
        "admin": {
            "username": "admin",
            "standard_password": None,
            "preconfig_password": None,
        },
    }
    assert nc.get_service_accounts() == {
        "account_a": {"username": "svc-a", "password": "svc-pw"},
        "account_b": {"username": None, "password": None},
    }
