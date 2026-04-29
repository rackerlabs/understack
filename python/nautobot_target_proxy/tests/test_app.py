from fastapi.testclient import TestClient

from nautobot_target_proxy import app as app_module


class _ResponseStub:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def test_get_oob_targets_returns_expected_payload(monkeypatch):
    monkeypatch.setenv("NAUTOBOT_LOCATION", "dev")
    monkeypatch.setenv("UNDERSTACK_PARTITION", "dfw")

    payload = {
        "data": {
            "interfaces": [
                {
                    "device": {
                        "name": "server-01",
                        "rack": {"name": "rack-a1"},
                        "id": "device-uuid-1",
                        "cpf_urn": "urn:rackspace:server-01",
                        "location": {"name": "dfw1"},
                    },
                    "ip_addresses": [
                        {"host": "192.0.2.10"},
                        {"host": "192.0.2.11"},
                    ],
                },
                {
                    "device": {
                        "name": "server-02",
                        "rack": {"name": "rack-a2"},
                        "id": "device-uuid-2",
                        "cpf_urn": None,
                        "location": {"name": "dfw1"},
                    },
                    "ip_addresses": [
                        {"host": "192.0.2.12"},
                    ],
                },
            ]
        }
    }

    def fake_query(query, variables):
        assert variables == {"location": ["dev"]}
        return _ResponseStub(payload)

    monkeypatch.setattr(app_module, "query_nautobot_graphql", fake_query)
    client = TestClient(app_module.app)

    response = client.get("/targets/oob")

    assert response.status_code == 200
    assert response.json() == [
        {
            "targets": ["192.0.2.10"],
            "labels": {
                "device_name": "server-01",
                "uuid": "device-uuid-1",
                "location": "dfw1",
                "rack": "rack-a1",
                "urn": "urn:rackspace:server-01",
            },
        },
        {
            "targets": ["192.0.2.11"],
            "labels": {
                "device_name": "server-01",
                "uuid": "device-uuid-1",
                "location": "dfw1",
                "rack": "rack-a1",
                "urn": "urn:rackspace:server-01",
            },
        },
    ]


def test_get_oob_targets_requires_nautobot_location(monkeypatch):
    monkeypatch.delenv("NAUTOBOT_LOCATION", raising=False)
    client = TestClient(app_module.app, raise_server_exceptions=False)

    response = client.get("/targets/oob")

    assert response.status_code == 500
    assert response.json()["error"] is True
    assert "NAUTOBOT_LOCATION is required" in response.json()["detail"]
