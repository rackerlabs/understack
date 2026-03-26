"""File-backed OIDC access token plugin for keystoneauth."""

from __future__ import annotations

from keystoneauth1 import exceptions, loading
from keystoneauth1.identity.v3 import oidc
from keystoneauth1.loading._plugins.identity import v3 as identity_v3_loading


class OpenIDConnectAccessTokenFile(oidc.OidcAccessToken):
    """OIDC access-token auth plugin that reads the token from a file."""

    def __init__(
        self, *args, access_token_file: str, access_token: str | None = None, **kwargs
    ):
        if not access_token_file:
            raise exceptions.OptionError("'access_token_file' is required")

        self.access_token_file = access_token_file

        super().__init__(*args, access_token=access_token or "", **kwargs)

    def _read_access_token(self) -> str:
        try:
            with open(self.access_token_file, encoding="utf-8") as token_file:
                token = token_file.read().strip()
        except FileNotFoundError as exc:
            msg = f"OIDC access token file does not exist: {self.access_token_file}"
            raise exceptions.AuthorizationFailure(msg) from exc
        except OSError as exc:
            msg = (
                "Unable to read OIDC access token file "
                f"'{self.access_token_file}': {exc}"
            )
            raise exceptions.AuthorizationFailure(msg) from exc

        if not token:
            msg = f"OIDC access token file is empty: {self.access_token_file}"
            raise exceptions.AuthorizationFailure(msg)

        return token

    def get_unscoped_auth_ref(self, session):
        self.access_token = self._read_access_token()
        return super().get_unscoped_auth_ref(session)


class OpenIDConnectAccessTokenFileLoader(identity_v3_loading.OpenIDConnectAccessToken):
    """Loader for the file-backed OIDC access-token auth plugin."""

    @property
    def plugin_class(self):
        return OpenIDConnectAccessTokenFile

    def get_options(self):
        options = [
            option for option in super().get_options() if option.dest != "access_token"
        ]

        options.append(
            loading.Opt(
                "access-token-file",
                required=True,
                help="Path to a file containing the OIDC access token.",
            )
        )
        return options
