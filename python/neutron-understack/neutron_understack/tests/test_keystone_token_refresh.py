from unittest.mock import Mock

import pytest

from neutron_understack.undersync_client import Undersync


@pytest.fixture
def undersync(mocker):
    mock_session = Mock()
    mock_session.post.return_value.status_code = 200
    mock_session.post.return_value.json.return_value = {"result": "success"}
    mocker.patch("neutron_understack.config.get_session", return_value=mock_session)
    return Undersync("http://test-api")


class TestKeystoneTokenRefresh:
    """Test that each Undersync request goes through the keystoneauth1 session."""

    @pytest.mark.usefixtures("_ml2_understack_conf")
    def test_undersync_uses_session_per_request(self, undersync):
        """Test that sync calls _session.post, for token refresh.

        By calling _session.post directly, keystoneauth1 handles token refresh
        transparently rather than us caching a token manually.
        """
        result1 = undersync.sync("vlan-group-1")
        result2 = undersync.sync("vlan-group-2")

        assert undersync._session.post.call_count == 2
        assert result1.status_code == 200
        assert result2.status_code == 200

    def test_disabled_undersync_does_not_use_session(self, oslo_config, undersync):
        oslo_config.config(undersync_disabled=True, group="ml2_understack")

        assert undersync.sync("vlan-group-1") is None

        undersync._session.post.assert_not_called()
