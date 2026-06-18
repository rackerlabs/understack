from unittest.mock import Mock

import pytest

from neutron_understack.undersync import Undersync


@pytest.fixture
def undersync(mocker):
    mock_session = Mock()
    mock_session.get_token.return_value = "test_token"
    mocker.patch("neutron_understack.config.get_session", return_value=mock_session)
    return Undersync("http://test-api")


class TestKeystoneTokenRefresh:
    """Test that each Undersync request gets a fresh token from the session."""

    def test_undersync_refreshes_token_per_request(self, mocker, undersync):
        """Test that sync_devices calls get_token() on each request.

        The client property calls get_token() each time it is accessed, so
        tokens are never cached — each request gets a fresh token from keystoneauth1.
        """
        mock_post = mocker.patch("requests.Session.post")
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"result": "success"}

        result1 = undersync.sync_devices("vlan-group-1")
        result2 = undersync.sync_devices("vlan-group-2")

        assert undersync._session.get_token.call_count == 2
        assert result1.status_code == 200
        assert result2.status_code == 200
        assert len(mock_post.call_args_list) == 2
