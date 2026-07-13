from unittest.mock import Mock

import pytest
import requests

from ironic_understack.kea_proxy import kea_client


@pytest.fixture(autouse=True)
def _max_retries():
    kea_client.CONF.set_override("kea_max_retries", 3, group="ironic_understack")
    yield
    kea_client.CONF.clear_override("kea_max_retries", group="ironic_understack")


@pytest.fixture
def lookup_urls(mocker):
    return mocker.patch.object(
        kea_client, "_lookup_api_urls", return_value=["http://kea"]
    )


def _response(payload):
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = payload
    return response


def test_make_request_retries_after_transient_timeout(lookup_urls, mocker):
    post = mocker.patch(
        "ironic_understack.kea_proxy.kea_client.requests.post",
        side_effect=[requests.exceptions.Timeout(), _response({"result": 0})],
    )

    result = kea_client._make_request("config-get", {})

    assert result == {"result": 0}
    assert post.call_count == 2


def test_make_request_raises_after_exhausting_retries(lookup_urls, mocker):
    post = mocker.patch(
        "ironic_understack.kea_proxy.kea_client.requests.post",
        side_effect=requests.exceptions.ConnectionError("boom"),
    )

    with pytest.raises(kea_client.KeaRequestError):
        kea_client._make_request("config-get", {})

    assert post.call_count == 3


def test_make_request_raises_after_exhausting_timeouts(lookup_urls, mocker):
    post = mocker.patch(
        "ironic_understack.kea_proxy.kea_client.requests.post",
        side_effect=requests.exceptions.Timeout(),
    )

    with pytest.raises(kea_client.KeaRequestError):
        kea_client._make_request("config-get", {})

    assert post.call_count == 3


def test_make_request_succeeds_on_first_attempt(lookup_urls, mocker):
    post = mocker.patch(
        "ironic_understack.kea_proxy.kea_client.requests.post",
        return_value=_response({"result": 0}),
    )

    result = kea_client._make_request("config-get", {})

    assert result == {"result": 0}
    assert post.call_count == 1


def test_update_reservation_updates_existing_entry(mocker):
    other_reservation = {
        "hw-address": "aa:aa:aa:aa:aa:aa",
        "client-classes": ["BOOTSRV_A"],
    }
    target_reservation = {
        "hw-address": "bb:bb:bb:bb:bb:bb",
        "client-classes": ["BOOTSRV_A"],
    }
    config = {
        "arguments": {
            "hash": "somehash",
            "Dhcp4": {"reservations": [other_reservation, target_reservation]},
        }
    }
    mocker.patch.object(kea_client, "get_config", return_value=config)
    set_config = mocker.patch.object(kea_client, "set_config")
    save_config = mocker.patch.object(kea_client, "save_config")

    kea_client.update_reservation("bb:bb:bb:bb:bb:bb", "BOOTSRV_B")

    sent_config = set_config.call_args[0][0]
    assert sent_config["Dhcp4"]["reservations"] == [
        other_reservation,
        {"hw-address": "bb:bb:bb:bb:bb:bb", "client-classes": ["BOOTSRV_B"]},
    ]
    save_config.assert_called_once()


def test_update_reservation_creates_new_entry(mocker):
    config = {"arguments": {"hash": "somehash", "Dhcp4": {"reservations": []}}}
    mocker.patch.object(kea_client, "get_config", return_value=config)
    set_config = mocker.patch.object(kea_client, "set_config")
    mocker.patch.object(kea_client, "save_config")

    kea_client.update_reservation("cc:cc:cc:cc:cc:cc", "BOOTSRV_A")

    sent_config = set_config.call_args[0][0]
    assert sent_config["Dhcp4"]["reservations"] == [
        {"hw-address": "cc:cc:cc:cc:cc:cc", "client-classes": ["BOOTSRV_A"]}
    ]


def test_delete_reservation_removes_existing_entry(mocker):
    other_reservation = {
        "hw-address": "aa:aa:aa:aa:aa:aa",
        "client-classes": ["BOOTSRV_A"],
    }
    target_reservation = {
        "hw-address": "bb:bb:bb:bb:bb:bb",
        "client-classes": ["BOOTSRV_A"],
    }
    config = {
        "arguments": {
            "hash": "somehash",
            "Dhcp4": {"reservations": [other_reservation, target_reservation]},
        }
    }
    mocker.patch.object(kea_client, "get_config", return_value=config)
    set_config = mocker.patch.object(kea_client, "set_config")
    save_config = mocker.patch.object(kea_client, "save_config")

    kea_client.delete_reservation("bb:bb:bb:bb:bb:bb")

    sent_config = set_config.call_args[0][0]
    assert sent_config["Dhcp4"]["reservations"] == [other_reservation]
    save_config.assert_called_once()


def test_delete_reservation_missing_entry_is_noop(mocker):
    config = {"arguments": {"hash": "somehash", "Dhcp4": {"reservations": []}}}
    mocker.patch.object(kea_client, "get_config", return_value=config)
    set_config = mocker.patch.object(kea_client, "set_config")
    save_config = mocker.patch.object(kea_client, "save_config")

    kea_client.delete_reservation("dd:dd:dd:dd:dd:dd")

    set_config.assert_not_called()
    save_config.assert_not_called()


def test_get_leases_merges_v4_and_v6(mocker):
    def fake_make_request(command, arguments, services=None):
        if command == "lease4-get":
            return {"arguments": {"leases": [{"ip-address": "10.0.0.5"}]}}
        return {"arguments": {"leases": [{"ip-addresses": ["fd00::5"]}]}}

    mocker.patch.object(kea_client, "_make_request", side_effect=fake_make_request)

    addresses = kea_client.get_leases("aa:bb:cc:dd:ee:ff")

    assert addresses == ["10.0.0.5", "fd00::5"]


def test_get_leases_tolerates_family_failure(mocker):
    def fake_make_request(command, arguments, services=None):
        if command == "lease4-get":
            return {"arguments": {"leases": [{"ip-address": "10.0.0.5"}]}}
        raise kea_client.KeaRequestError("dhcp6 unavailable")

    mocker.patch.object(kea_client, "_make_request", side_effect=fake_make_request)

    addresses = kea_client.get_leases("aa:bb:cc:dd:ee:ff")

    assert addresses == ["10.0.0.5"]
