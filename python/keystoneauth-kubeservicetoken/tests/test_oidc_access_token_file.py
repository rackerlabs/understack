from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from keystoneauth1 import exceptions, loading
from keystoneauth1.identity.v3 import oidc as upstream_oidc

from keystoneauth_kubeservicetoken.oidc import (
    OpenIDConnectAccessTokenFile,
    OpenIDConnectAccessTokenFileLoader,
)


class FakeAuthRef:
    def __init__(self, auth_token: str, expires_soon: bool):
        self.auth_token = auth_token
        self._expires_soon = expires_soon

    def will_expire_soon(self, _stale_duration: int) -> bool:
        return self._expires_soon


def _create_plugin(token_file: Path) -> OpenIDConnectAccessTokenFile:
    return OpenIDConnectAccessTokenFile(
        auth_url="https://keystone.example/v3",
        identity_provider="example-idp",
        protocol="openid",
        access_token_file=str(token_file),
    )


@pytest.fixture
def auth_options() -> dict[str, str]:
    return {
        "auth_url": "https://keystone.example/v3",
        "identity_provider": "example-idp",
        "protocol": "openid",
    }


def test_loader_options_require_access_token_file_and_not_access_token():
    loader = OpenIDConnectAccessTokenFileLoader()

    options = {option.dest: option for option in loader.get_options()}

    assert "access_token_file" in options
    assert options["access_token_file"].required
    assert "access_token" not in options


def test_loader_can_initialize_plugin_with_access_token_file_only(
    tmp_path, auth_options
):
    token_file = tmp_path / "token"
    token_file.write_text("oidc-token", encoding="utf-8")

    loader = OpenIDConnectAccessTokenFileLoader()
    plugin = loader.load_from_options(
        **auth_options,
        access_token_file=str(token_file),
    )

    assert isinstance(plugin, OpenIDConnectAccessTokenFile)
    assert plugin.access_token_file == str(token_file)


def test_plugin_loader_is_discoverable_by_auth_type():
    loader = loading.get_plugin_loader("v3oidcaccesstokenfile")

    assert isinstance(loader, OpenIDConnectAccessTokenFileLoader)


def test_missing_access_token_file_configuration_fails(auth_options):
    with pytest.raises(exceptions.OptionError, match="access_token_file"):
        OpenIDConnectAccessTokenFile(
            **auth_options,
            access_token_file="",
        )


def test_auth_reads_trimmed_token_from_file_each_time(tmp_path):
    token_file = tmp_path / "token"
    token_file.write_text(" token-a\n", encoding="utf-8")

    plugin = _create_plugin(token_file)
    observed_tokens: list[str] = []

    def fake_super_get_unscoped_auth_ref(self, _session):
        observed_tokens.append(self.access_token)
        return object()

    with patch.object(
        upstream_oidc.OidcAccessToken,
        "get_unscoped_auth_ref",
        autospec=True,
        side_effect=fake_super_get_unscoped_auth_ref,
    ):
        plugin.get_unscoped_auth_ref(session=None)
        token_file.write_text("token-b\n", encoding="utf-8")
        plugin.get_unscoped_auth_ref(session=None)

    assert observed_tokens == ["token-a", "token-b"]


def test_auth_fails_for_missing_file(tmp_path):
    plugin = _create_plugin(tmp_path / "missing-token")

    with pytest.raises(exceptions.AuthorizationFailure, match="does not exist"):
        plugin._read_access_token()


def test_auth_fails_for_unreadable_file(tmp_path):
    token_file = tmp_path / "token"
    token_file.write_text("token", encoding="utf-8")
    plugin = _create_plugin(token_file)

    with patch("builtins.open", side_effect=OSError("permission denied")):
        with pytest.raises(exceptions.AuthorizationFailure, match="Unable to read"):
            plugin._read_access_token()


def test_auth_fails_for_empty_file(tmp_path):
    token_file = tmp_path / "token"
    token_file.write_text("\n\t", encoding="utf-8")
    plugin = _create_plugin(token_file)

    with pytest.raises(exceptions.AuthorizationFailure, match="is empty"):
        plugin._read_access_token()


def test_file_updates_consumed_on_reauth_not_every_request(tmp_path):
    token_file = tmp_path / "token"
    token_file.write_text("token-a", encoding="utf-8")
    plugin = _create_plugin(token_file)

    plugin.auth_ref = FakeAuthRef(
        auth_token="cached-keystone-token", expires_soon=False
    )

    def fake_get_auth_ref(_session):
        plugin.get_unscoped_auth_ref(session=None)
        return FakeAuthRef(auth_token=f"ks-{plugin.access_token}", expires_soon=False)

    with (
        patch.object(
            upstream_oidc.OidcAccessToken,
            "get_unscoped_auth_ref",
            autospec=True,
            return_value=object(),
        ),
        patch.object(plugin, "get_auth_ref", side_effect=fake_get_auth_ref),
    ):
        token_file.write_text("token-b", encoding="utf-8")

        assert plugin.get_token(session=None) == "cached-keystone-token"

        plugin.auth_ref = FakeAuthRef(auth_token="expiring-token", expires_soon=True)
        assert plugin.get_token(session=None) == "ks-token-b"
