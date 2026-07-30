import pytest

from us_net import osclient


class FakeConfig:
    def __init__(self, data):
        self.config = data


class FakeConnection:
    def __init__(self, data):
        self.config = FakeConfig(data)


def test_describe_target_returns_auth_details(monkeypatch):
    fake_conn = FakeConnection(
        {
            "auth": {
                "auth_url": "https://example/v3",
                "project_name": "baremetal",
                "username": "doug",
            },
            "region_name": "dfw3",
        }
    )
    monkeypatch.setattr(osclient, "get_connection", lambda os_cloud: fake_conn)
    pairs = dict(osclient.describe_target("dev-cloud"))
    assert pairs["auth URL"] == "https://example/v3"
    assert pairs["region"] == "dfw3"
    assert pairs["project"] == "baremetal"
    assert pairs["username"] == "doug"


def test_describe_target_handles_connect_failure(monkeypatch):
    def boom(os_cloud):
        raise RuntimeError("no cloud configured")

    monkeypatch.setattr(osclient, "get_connection", boom)
    pairs = dict(osclient.describe_target("dev-cloud"))
    assert "unavailable" in pairs["status"]


def test_describe_target_handles_empty_auth(monkeypatch):
    monkeypatch.setattr(osclient, "get_connection", lambda os_cloud: FakeConnection({}))
    pairs = dict(osclient.describe_target("dev-cloud"))
    assert "no auth details" in pairs["status"]


def test_resolve_router_found():
    class FakeRouter:
        id = "abc"

    class FakeNetwork:
        def find_router(self, name_or_id):
            return FakeRouter()

    class FakeConn:
        network = FakeNetwork()

    router = osclient.resolve_router(FakeConn(), "my-router")
    assert router.id == "abc"


def test_resolve_router_not_found_raises():
    class FakeNetwork:
        def find_router(self, name_or_id):
            return None

    class FakeConn:
        network = FakeNetwork()

    with pytest.raises(LookupError):
        osclient.resolve_router(FakeConn(), "missing-router")
