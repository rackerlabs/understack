import pytest
from webtest import TestApp

from ironic_understack.kea_proxy import app
from ironic_understack.kea_proxy import kea_client


@pytest.fixture
def client():
    return TestApp(app.make_app())


def test_update_reservation_success(client, mocker):
    update_reservation = mocker.patch.object(kea_client, "update_reservation")

    response = client.post_json(
        "/v1/update_reservation",
        {"hw-address": "aa:bb:cc:dd:ee:ff", "client_class": "BOOTSRV_A"},
    )

    assert response.status_int == 200
    assert response.json == {"result": "ok"}
    update_reservation.assert_called_once_with("aa:bb:cc:dd:ee:ff", "BOOTSRV_A")


def test_update_reservation_missing_fields(client):
    response = client.post_json("/v1/update_reservation", {}, expect_errors=True)

    assert response.status_int == 400
    assert "error" in response.json


def test_update_reservation_kea_failure(client, mocker):
    mocker.patch.object(
        kea_client,
        "update_reservation",
        side_effect=kea_client.KeaRequestError("boom"),
    )

    response = client.post_json(
        "/v1/update_reservation",
        {"hw-address": "aa:bb:cc:dd:ee:ff", "client_class": "BOOTSRV_A"},
        expect_errors=True,
    )

    assert response.status_int == 500
    assert response.json == {"error": "boom"}


def test_get_leases_success(client, mocker):
    mocker.patch.object(kea_client, "get_leases", return_value=["10.0.0.5"])

    response = client.get("/v1/leases", params={"mac": "aa:bb:cc:dd:ee:ff"})

    assert response.status_int == 200
    assert response.json == {"addresses": ["10.0.0.5"]}


def test_get_leases_missing_mac(client):
    response = client.get("/v1/leases", expect_errors=True)

    assert response.status_int == 400
    assert "error" in response.json


def test_delete_lease_success(client, mocker):
    delete_reservation = mocker.patch.object(kea_client, "delete_reservation")

    response = client.delete_json("/v1/leases", {"hw-address": "aa:bb:cc:dd:ee:ff"})

    assert response.status_int == 200
    assert response.json == {"result": "ok"}
    delete_reservation.assert_called_once_with("aa:bb:cc:dd:ee:ff")


def test_delete_lease_missing_hw_address(client):
    response = client.delete_json("/v1/leases", {}, expect_errors=True)

    assert response.status_int == 400
    assert "error" in response.json


def test_delete_lease_kea_failure(client, mocker):
    mocker.patch.object(
        kea_client,
        "delete_reservation",
        side_effect=kea_client.KeaRequestError("boom"),
    )

    response = client.delete_json(
        "/v1/leases", {"hw-address": "aa:bb:cc:dd:ee:ff"}, expect_errors=True
    )

    assert response.status_int == 500
    assert response.json == {"error": "boom"}
