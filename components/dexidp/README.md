# Overview

The [Dex IDP](https://dexidp.io/) is deployed to act as an OAuth2/OpenID
Connect identity provider for Nautobot and potentially other applications in
the environment. With the default setup, it is backed by the
[Keystone][keystone] component where the
actual accounts are stored. Having it setup this way, we do not have to
manually sync the accounts across components. It should also allow us to
configure SSO with systems other than Keystone by using one of [multiple Dex
connectors][connectors].

[keystone]: https://docs.openstack.org/keystone/latest/
[connectors]: https://dexidp.io/docs/connectors/

## Nautobot setup

In order to use dexidp as the authentication system we needed to make bunch of
adjustments on the Nautobot side. In summary, this creates following
requirements:

- `nautobot_config.py` needs to be adjusted, so that it:
    1. Uses [OIDC Social Auth][socialauth] backend.
    2. Has a configuration pointing to the Dex [OpenID Discovery][disco] URL.
    3. Injects custom authentication pipeline step that is responsible for
       synchronizing the `Groups` from the information provided by Dex.
- custom auth pipeline needs to be created and injected into environemtn

Unfortunately, these Nautobot changes alone are not enough to have
authentication working in most setups. We also need to make sure that every
step of [authorziation code grant][authzcodegrant] can be completed.

For ephemeral clusters in development it is recommended to use a service like
[sslip.io](https://sslip.io) to use hostnames like:

- dex.127-0-0-1.sslip.io
- nautobot-127-0-0-1.sslip.io

And creating HTTPS certificates for them. Then you can access the services
via DNS names and not have to patch your `/etc/hosts` or the DNS resolution in the cluster.

## Azure authentication

Dex can optionally be configured to allow authentication through Azure SSO. The
exact steps to configure this are available in
[01-secrets/README.md](../01-secrets/README.md).

[socialauth]: https://python-social-auth.readthedocs.io/en/latest/backends/oidc.html
[disco]: https://openid.net/specs/openid-connect-discovery-1_0.html
[authzcodegrant]: https://datatracker.ietf.org/doc/html/rfc6749#section-4.1
