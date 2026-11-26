from unittest.mock import Mock

import pytest

from ironic_understack.utils import nxos_api


def _response(status=200, json=None):
    resp = Mock(status_code=status)
    if json is None:
        resp.json.side_effect = ValueError("no json")
    else:
        resp.json.return_value = json
    return resp


def _client(resp):
    session = Mock()
    session.post.return_value = resp
    client = nxos_api.NxosClient("192.0.2.20", "svc", "example-pw", session=session)
    return client, session


def test_show_sends_json_rpc():
    client, session = _client(
        _response(json={"jsonrpc": "2.0", "result": {"body": {"a": 1}}, "id": 1})
    )

    assert client.show("show version") == {"a": 1}

    session.post.assert_called_once()
    args, kwargs = session.post.call_args
    assert args == ("https://192.0.2.20/ins",)
    assert kwargs["json"][0]["method"] == "cli"
    assert kwargs["json"][0]["params"] == {"cmd": "show version", "version": 1}
    assert session.auth == ("svc", "example-pw")
    assert session.verify is False


def test_show_refuses_non_show_commands():
    client, session = _client(_response(json={}))
    with pytest.raises(ValueError, match="only show commands"):
        client.show("configure terminal")
    session.post.assert_not_called()


def test_show_reports_nxapi_error():
    client, _ = _client(
        _response(
            status=500,
            json={
                "jsonrpc": "2.0",
                "error": {
                    "code": -32602,
                    "message": "Invalid params",
                    "data": {"msg": "% Invalid command"},
                },
                "id": 1,
            },
        )
    )
    with pytest.raises(nxos_api.NxosApiError, match="Invalid command"):
        client.show("show bogus")


def test_show_reports_bad_credentials():
    client, _ = _client(_response(status=401))
    with pytest.raises(nxos_api.NxosApiError, match="credentials"):
        client.show("show version")


def test_show_null_result_is_empty():
    client, _ = _client(_response(json={"jsonrpc": "2.0", "result": None, "id": 1}))
    assert client.show("show interface") == {}


def test_parse_ethernet_interfaces_uses_burned_in_mac():
    body = {
        "TABLE_interface": {
            "ROW_interface": [
                {"interface": "mgmt0", "eth_hw_addr": "00de.fb00.0001"},
                {
                    "interface": "Ethernet1/1",
                    "eth_hw_addr": "00de.fb00.0000",
                    "eth_bia_addr": "00de.fb00.0101",
                },
                {"interface": "Ethernet1/49/1", "eth_hw_addr": "00de.fb00.0149"},
                {"interface": "Ethernet1/2"},
                {"interface": "Ethernet1/3", "eth_bia_addr": 12},
                {"interface": "port-channel10", "eth_hw_addr": "00de.fb00.0010"},
                {"interface": "Vlan100", "eth_hw_addr": "00de.fb00.0000"},
            ]
        }
    }

    assert nxos_api.parse_ethernet_interfaces(body) == [
        {"interface": "Ethernet1/1", "mac": "00:de:fb:00:01:01"},
        {"interface": "Ethernet1/49/1", "mac": "00:de:fb:00:01:49"},
    ]


@pytest.mark.parametrize("key", ["vdc_mac", "mac", "switch_mac"])
def test_parse_chassis_mac_field_names(key):
    body = {"TABLE_vdc": {"ROW_vdc": {"vdc_id": "1", key: "f45b.b400.0000"}}}
    assert nxos_api.parse_chassis_mac(body) == "f4:5b:b4:00:00:00"


def test_parse_chassis_mac_prefers_the_default_vdc():
    body = {
        "TABLE_vdc": {
            "ROW_vdc": [
                {"vdc_id": "2", "mac": "f45b.b400.0002"},
                {"vdc_id": "1", "mac": "f45b.b400.0001"},
            ]
        }
    }
    assert nxos_api.parse_chassis_mac(body) == "f4:5b:b4:00:00:01"


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"TABLE_vdc": {"ROW_vdc": {"vdc_id": "1", "max_mac": 100}}},
        {"TABLE_vdc": {"ROW_vdc": {"vdc_id": "1", "vdc_mac": {"a": "b"}}}},
        {"TABLE_vdc": {"ROW_vdc": {"vdc_id": "1", "mac": "unknown"}}},
    ],
    ids=["empty", "number", "dict", "not-a-mac"],
)
def test_parse_chassis_mac_not_reported(body):
    assert nxos_api.parse_chassis_mac(body) is None


@pytest.mark.parametrize(
    ("config", "expected"),
    [
        ("feature lldp\nlldp chassis-id switch\n", "switch"),
        ("feature lldp\nlldp timer 10\n", "interface"),
        ("!Command: show running-config lldp\n\nfeature lldp\n", "interface"),
    ],
    ids=["switch", "default", "header-only"],
)
def test_parse_lldp_chassis_id(config, expected):
    assert nxos_api.parse_lldp_chassis_id(config) == expected


def test_show_text_uses_cli_ascii():
    client, session = _client(_response(json={"result": {"msg": "text\n"}}))
    assert client.show_text("show running-config lldp") == "text\n"
    assert session.post.call_args.kwargs["json"][0]["method"] == "cli_ascii"


def test_show_text_raises_the_command_error():
    client, _ = _client(
        _response(status=500, json={"error": {"message": "Invalid"}, "id": 1})
    )
    with pytest.raises(nxos_api.NxosApiError, match="Invalid"):
        client.show_text("show running-config lldp")


def test_show_many_batches_into_one_request():
    client, session = _client(
        _response(
            json=[
                {"result": {"body": {"v": 1}}, "id": 1},
                {"result": {"body": {"i": 2}}, "id": 2},
            ]
        )
    )

    assert client.show_many(["show version", "show interface"]) == [
        {"v": 1},
        {"i": 2},
    ]
    session.post.assert_called_once()
    payload = session.post.call_args.kwargs["json"]
    assert [(e["id"], e["method"], e["params"]["cmd"]) for e in payload] == [
        (1, "cli", "show version"),
        (2, "cli", "show interface"),
    ]


def test_show_many_returns_each_commands_error():
    # NX-API answers a batch with a partial failure with HTTP 500.
    client, _ = _client(
        _response(
            status=500,
            json=[
                {"result": {"body": {"v": 1}}, "id": 1},
                {"error": {"message": "x", "data": {"msg": "% Invalid"}}, "id": 2},
            ],
        )
    )

    version, vdc, missing = client.show_many(
        ["show version", "show vdc detail", "show interface"]
    )

    # An HTTP error status taints even an answer without its own error.
    assert isinstance(version, nxos_api.NxosApiError)
    assert "HTTP 500" in str(version)
    assert isinstance(vdc, nxos_api.NxosApiError)
    assert "show vdc detail" in str(vdc)
    assert "Invalid" in str(vdc)
    assert isinstance(missing, nxos_api.NxosApiError)
    assert "no response" in str(missing)


def test_show_many_matches_answers_by_id():
    client, _ = _client(
        _response(
            json=[
                {"result": {"body": {"i": 2}}, "id": "2"},
                {"result": {"body": {"v": 1}}, "id": "1"},
            ]
        )
    )
    assert client.show_many(["show version", "show interface"]) == [
        {"v": 1},
        {"i": 2},
    ]


def test_client_closes_its_session():
    client, session = _client(_response(json={}))
    with client:
        pass
    session.close.assert_called_once()


def test_rows_handles_a_lone_row():
    body = {"TABLE_x": {"ROW_x": {"k": "v"}}}
    assert nxos_api.rows(body, "TABLE_x", "ROW_x") == [{"k": "v"}]
    assert nxos_api.rows({}, "TABLE_x", "ROW_x") == []


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("00de.fb12.3456", "00:de:fb:12:34:56"),
        ("00:DE:FB:12:34:56", "00:de:fb:12:34:56"),
    ],
)
def test_normalize_mac(raw, expected):
    assert nxos_api.normalize_mac(raw) == expected


def test_normalize_mac_rejects_garbage():
    with pytest.raises(ValueError, match="not a MAC"):
        nxos_api.normalize_mac("not-a-mac")


def test_non_json_error_is_an_api_error():
    client, _ = _client(_response(status=502))
    with pytest.raises(nxos_api.NxosApiError, match="HTTP 502"):
        client.show("show version")


def test_non_json_success_is_an_api_error():
    client, _ = _client(_response(status=200))
    with pytest.raises(nxos_api.NxosApiError, match="not JSON"):
        client.show("show version")


def test_list_wrapped_response_is_accepted():
    client, _ = _client(_response(json=[{"result": {"body": {"a": 1}}}]))
    assert client.show("show version") == {"a": 1}


def test_show_text_rejects_structured_output():
    client, _ = _client(_response(json={"result": {"body": {"a": 1}}}))
    with pytest.raises(nxos_api.NxosApiError, match="expected text"):
        client.show_text("show running-config lldp")


def test_show_version():
    client, session = _client(_response(json={"result": {"body": {"v": "1"}}}))
    assert client.show_version() == {"v": "1"}
    assert session.post.call_args.kwargs["json"][0]["params"]["cmd"] == ("show version")
