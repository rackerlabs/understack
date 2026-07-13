from unittest.mock import Mock

import pytest
import requests
from ironic import objects

from ironic_understack.conf import CONF
from ironic_understack.dhcp.kea import DEFAULT_CLIENT_CLASS
from ironic_understack.dhcp.kea import DHCPConfigurationError
from ironic_understack.dhcp.kea import KeaDHCPApi

# objects.Port is only registered as an attribute once ironic.objects.port
# has been imported (see ironic.objects.register_all).
objects.register_all()

PROXY_URL = "http://kea-proxy:9080"


@pytest.fixture(autouse=True)
def _proxy_url():
    CONF.set_override("kea_proxy_url", PROXY_URL, group="ironic_understack")
    yield
    CONF.clear_override("kea_proxy_url", group="ironic_understack")


@pytest.fixture
def kea():
    api = KeaDHCPApi()
    api.max_retries = 3
    return api


def _response(status_code=200, payload=None):
    response = Mock()
    if status_code >= 400:
        response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=Mock(status_code=status_code)
        )
    else:
        response.raise_for_status.return_value = None
    response.json.return_value = payload or {}
    return response


def test_request_retries_after_transient_timeout(kea, mocker):
    request = mocker.patch(
        "ironic_understack.dhcp.kea.requests.request",
        side_effect=[
            requests.exceptions.Timeout(),
            _response(payload={"result": "ok"}),
        ],
    )

    result = kea._request("POST", "/v1/update_reservation", json={})

    assert result == {"result": "ok"}
    assert request.call_count == 2


def test_request_raises_after_exhausting_retries(kea, mocker):
    request = mocker.patch(
        "ironic_understack.dhcp.kea.requests.request",
        side_effect=requests.exceptions.ConnectionError("boom"),
    )

    with pytest.raises(DHCPConfigurationError):
        kea._request("GET", "/v1/leases")

    assert request.call_count == kea.max_retries


def test_update_port_dhcp_opts_posts_reservation(kea, mocker):
    port = Mock(address="aa:bb:cc:dd:ee:ff")
    mocker.patch("ironic_understack.dhcp.kea.objects.Port.get", return_value=port)
    request = mocker.patch(
        "ironic_understack.dhcp.kea.requests.request",
        return_value=_response(payload={"result": "ok"}),
    )

    result = kea.update_port_dhcp_opts("port-id", [])

    assert result is True
    args, kwargs = request.call_args
    assert args == ("POST", f"{PROXY_URL}/v1/update_reservation")
    assert kwargs["json"] == {
        "hw-address": "aa:bb:cc:dd:ee:ff",
        "client_class": DEFAULT_CLIENT_CLASS,
    }


def test_update_port_dhcp_opts_returns_false_on_failure(kea, mocker):
    port = Mock(address="aa:bb:cc:dd:ee:ff")
    mocker.patch("ironic_understack.dhcp.kea.objects.Port.get", return_value=port)
    mocker.patch(
        "ironic_understack.dhcp.kea.requests.request",
        side_effect=requests.exceptions.ConnectionError("boom"),
    )

    assert kea.update_port_dhcp_opts("port-id", []) is False


def test_clean_dhcp_opts_deletes_leases_for_each_port(kea, mocker):
    task = Mock()
    task.ports = [Mock(address="aa:bb:cc:dd:ee:ff", uuid="port-1")]
    request = mocker.patch(
        "ironic_understack.dhcp.kea.requests.request",
        return_value=_response(payload={"result": "ok"}),
    )

    assert kea.clean_dhcp_opts(task) is True
    args, kwargs = request.call_args
    assert args == ("DELETE", f"{PROXY_URL}/v1/leases")
    assert kwargs["json"] == {"hw-address": "aa:bb:cc:dd:ee:ff"}


def test_clean_dhcp_opts_returns_false_on_failure(kea, mocker):
    task = Mock()
    task.ports = [Mock(address="aa:bb:cc:dd:ee:ff", uuid="port-1")]
    mocker.patch(
        "ironic_understack.dhcp.kea.requests.request",
        side_effect=requests.exceptions.ConnectionError("boom"),
    )

    assert kea.clean_dhcp_opts(task) is False


def test_get_ip_addresses_merges_ports(kea, mocker):
    task = Mock()
    task.ports = [Mock(address="aa:bb:cc:dd:ee:ff")]
    request = mocker.patch(
        "ironic_understack.dhcp.kea.requests.request",
        return_value=_response(payload={"addresses": ["10.0.0.5", "fd00::5"]}),
    )

    assert kea.get_ip_addresses(task) == ["10.0.0.5", "fd00::5"]
    args, kwargs = request.call_args
    assert args == ("GET", f"{PROXY_URL}/v1/leases")
    assert kwargs["params"] == {"mac": "aa:bb:cc:dd:ee:ff"}


def test_get_ip_addresses_tolerates_port_failure(kea, mocker):
    task = Mock()
    task.ports = [Mock(address="aa:bb:cc:dd:ee:ff")]
    mocker.patch(
        "ironic_understack.dhcp.kea.requests.request",
        side_effect=requests.exceptions.ConnectionError("boom"),
    )

    assert kea.get_ip_addresses(task) == []


def test_init_requires_kea_proxy_url():
    CONF.clear_override("kea_proxy_url", group="ironic_understack")
    CONF.set_override("kea_proxy_url", "", group="ironic_understack")

    with pytest.raises(DHCPConfigurationError):
        KeaDHCPApi()
