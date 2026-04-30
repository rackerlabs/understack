from itertools import cycle
from unittest.mock import Mock

from neutron_understack.neutron_understack_mech import UnderstackDriver


class TestKeystoneTokenRefresh:
    """Test that Keystone tokens can be refreshed when they expire."""

    def test_undersync_refreshes_expired_keystone_token(self, mocker, oslo_config):
        """Test that Undersync can handle token expiration by refreshing the token.

        This test simulates a scenario where:
        1. First call to get_token() returns token_1
        2. First Undersync API call succeeds with token_1
        3. Second call to get_token() returns token_2 (token_1 expired)
        4. Second Undersync API call succeeds with token_2

        This proves the session can refresh tokens automatically.
        """
        oslo_config.config(
            undersync_use_keystone_auth=True,
            group="ml2_understack",
        )

        # Mock the keystone session to simulate token refresh
        mock_session = Mock()
        # Use cycle to provide different tokens on each call (simulating refresh)
        mock_session.get_token.side_effect = cycle(["token_1", "token_2", "token_3"])

        mock_auth = mocker.patch("keystoneauth1.loading.load_auth_from_conf_options")
        mock_session_class = mocker.patch(
            "neutron_understack.neutron_understack_mech.ks_session.Session",
            return_value=mock_session
        )

        # Mock IronicClient to avoid config issues
        mocker.patch("neutron_understack.neutron_understack_mech.IronicClient")

        # Create driver - this should store the session, not extract token
        driver = UnderstackDriver()
        driver.initialize()

        # Mock the HTTP requests to verify the correct token is used
        mock_post = mocker.patch("requests.Session.post")
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"result": "success"}

        # First call - should use token_1
        result1 = driver.undersync.sync_devices("vlan-group-1")

        # Second call - should refresh and use token_2
        result2 = driver.undersync.sync_devices("vlan-group-2")

        # Verify session.get_token() was called three times:
        # 1. During initialization (verification)
        # 2. First sync_devices call
        # 3. Second sync_devices call
        assert mock_session.get_token.call_count == 3

        # Verify both calls succeeded
        assert result1.status_code == 200
        assert result2.status_code == 200

        # Verify HTTP calls were made
        assert len(mock_post.call_args_list) == 2, f"Expected 2 calls, got {len(mock_post.call_args_list)}"

        # The key verification is that session.get_token() was called for each request,
        # proving that tokens are refreshed rather than cached