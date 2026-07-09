from unittest.mock import Mock

import pytest
import requests

from ironic_understack.dhcp.kea import DHCPConfigurationError
from ironic_understack.dhcp.kea import KeaDHCPApi


@pytest.fixture
def kea(mocker):
    api = KeaDHCPApi()
    api.max_retries = 3
    mocker.patch.object(api, "_lookup_api_urls", return_value=["http://kea"])
    return api


def _response(payload):
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = payload
    return response


def test_make_request_retries_after_transient_timeout(kea, mocker):
    post = mocker.patch(
        "ironic_understack.dhcp.kea.requests.post",
        side_effect=[requests.exceptions.Timeout(), _response({"result": 0})],
    )

    result = kea._make_request("config-get", {})

    assert result == {"result": 0}
    assert post.call_count == 2


def test_make_request_raises_after_exhausting_retries(kea, mocker):
    post = mocker.patch(
        "ironic_understack.dhcp.kea.requests.post",
        side_effect=requests.exceptions.ConnectionError("boom"),
    )

    with pytest.raises(DHCPConfigurationError):
        kea._make_request("config-get", {})

    assert post.call_count == kea.max_retries


def test_make_request_raises_after_exhausting_timeouts(kea, mocker):
    post = mocker.patch(
        "ironic_understack.dhcp.kea.requests.post",
        side_effect=requests.exceptions.Timeout(),
    )

    with pytest.raises(DHCPConfigurationError):
        kea._make_request("config-get", {})

    assert post.call_count == kea.max_retries


def test_make_request_succeeds_on_first_attempt(kea, mocker):
    post = mocker.patch(
        "ironic_understack.dhcp.kea.requests.post",
        return_value=_response({"result": 0}),
    )

    result = kea._make_request("config-get", {})

    assert result == {"result": 0}
    assert post.call_count == 1
