## Overview

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
step of [authorziation code grant][authzcodegrant] can be completed. Given that
we use ephemeral clusters for development and they use `.local` domain,
following needs to work:

- Nautobot container can reach the Dex using the issuer URL (`https://dexidp.local`).
- End-user's browser must be able to reach Dex using exactly the same URL.
- Nautobot needs to be reachable using the DNS name, i.e. `https://nautobot.local`
- All of these needs to happen over HTTPS.

When Dex and Nautobot are hosted in the same cluster, by default they will try
to communicate over the internal networking and plain HTTP. This clearly
violates the requirements listed above, so we have to force the communication
between the pods to happen over the Ingress (which provides TLS termination and
stable hostname).

### Fixing DNS on development cluster

In development cluster, this can be done by reconfiguring [CoreDNS][coredns]
component. We have provided
[`scripts/patch-coredns.sh`](../../scripts/patch-coredns.sh) script to make the
necessary changes automatically.

```shell
$ ./scripts/patch-coredns.sh
[*] Patching coredns ConfigMap
configmap/coredns replaced
[*] Restarting CoreDNS
deployment.apps/coredns restarted
$
```

### Making components accessible from your machine

If running development cluster on your machine, you may need to create  create
an entry in your `/etc/hosts` file that looks similar to this:

```hosts
# Nautobot kind cluster
127.0.0.1 argocd.local nautobot.local keystone keystone.openstack dexidp.local workflows.local
```


### Azure authentication
Dex can optionally be configured to allow authentication through Azure SSO. The
exact steps to configure this are available in
[01-secrets/README.md](../01-secrets/README.md).

[socialauth]: https://python-social-auth.readthedocs.io/en/latest/backends/oidc.html
[disco]: https://openid.net/specs/openid-connect-discovery-1_0.html
[authzcodegrant]: https://datatracker.ietf.org/doc/html/rfc6749#section-4.1
[coredns]: https://kubernetes.io/docs/tasks/administer-cluster/coredns/#about-coredns
