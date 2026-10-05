from unittest.mock import Mock

import pytest

from understack_workflows.undersync.client import Undersync

API_URL = "http://undersync.example.com"


@pytest.fixture
def session():
    session = Mock()
    session.post.return_value.status_code = 200
    return session


@pytest.fixture
def undersync(session):
    return Undersync(session, api_url=API_URL)


@pytest.mark.parametrize(
    ("method", "action"),
    [("sync", "sync"), ("dry_run", "dry-run"), ("force", "force")],
)
def test_posts_to_action_endpoint(undersync, session, method, action):
    response = getattr(undersync, method)("a1-1-network")

    session.post.assert_called_once_with(
        f"{API_URL}/v1/vlan-group/a1-1-network/{action}", timeout=undersync.timeout
    )
    assert response is session.post.return_value


@pytest.mark.parametrize(
    ("kwargs", "action"),
    [
        ({}, "sync"),
        ({"force": True}, "force"),
        ({"dry_run": True}, "dry-run"),
        # dry_run wins so that a preview never pushes to the switches
        ({"force": True, "dry_run": True}, "dry-run"),
    ],
)
def test_sync_devices_dispatch(undersync, session, kwargs, action):
    undersync.sync_devices("a1-1-network", **kwargs)

    session.post.assert_called_once_with(
        f"{API_URL}/v1/vlan-group/a1-1-network/{action}", timeout=undersync.timeout
    )


def test_physical_network_is_escaped(undersync, session):
    undersync.sync("weird/name space")

    session.post.assert_called_once_with(
        f"{API_URL}/v1/vlan-group/weird%2Fname%20space/sync", timeout=undersync.timeout
    )


def test_raises_for_status(undersync, session):
    session.post.return_value.raise_for_status.side_effect = RuntimeError("boom")

    with pytest.raises(RuntimeError):
        undersync.sync("a1-1-network")


def test_each_request_goes_through_the_session(undersync, session):
    """keystoneauth1 handles token refresh, so we must not cache a token."""
    undersync.sync("a1-1-network")
    undersync.sync("a1-2-network")

    assert session.post.call_count == 2
