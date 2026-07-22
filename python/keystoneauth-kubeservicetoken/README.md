# File-backed OIDC access token plugin

This package provides a `keystoneauth1` plugin that extends the OIDC
access-token flow by reading the OIDC access token from a file
(`access_token_file`) at authentication and reauthentication time.

## Auth type

- `v3oidcaccesstokenfile`

## Required options

- `auth_url`
- `identity_provider`
- `protocol`
- `access_token_file`

## Service configuration examples

### Nova (`nova.conf`)

```ini
[service_user]
auth_type = v3oidcaccesstokenfile
auth_url = https://keystone.example/v3
identity_provider = k8s-workload-idp
protocol = openid
access_token_file = /var/run/secrets/openstack/nova-oidc-token
send_service_user_token = true
```

### Ironic -> Neutron client (`ironic.conf`)

```ini
[neutron]
auth_type = v3oidcaccesstokenfile
auth_url = https://keystone.internal:5000/v3
identity_provider = k8s-workload-idp
protocol = openid
access_token_file = /var/run/secrets/openstack/ironic-oidc-token
region_name = RegionOne
```

### Neutron -> Placement client (`neutron.conf`)

```ini
[placement]
auth_type = v3oidcaccesstokenfile
auth_url = https://keystone.example/v3
identity_provider = k8s-workload-idp
protocol = openid
access_token_file = /var/run/secrets/openstack/neutron-placement-oidc-token
valid_interfaces = internal
```

## Behavior notes

- Token content is read from file on authentication and reauthentication.
- Whitespace in the token file is trimmed.
- Missing, unreadable, or empty token files fail with an explicit auth error.
- Keystone token caching is preserved; token file updates are consumed when
  keystoneauth reauthenticates near Keystone token expiry.

## Rollout notes

1. Install this package where the OpenStack service runs.
2. Configure the service to use `auth_type = v3oidcaccesstokenfile`.
3. Set `access_token_file` to the rotated token file path. This will usually be
   path to where the Kubernetes secret is mounted.
4. Optionally verify at least one full Keystone token renewal cycle to confirm
   file updates are consumed.
