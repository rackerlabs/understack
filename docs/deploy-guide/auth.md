# Authentication and Authorization

You must configure how users and operators will authenticate against the various services
provided by Understack. At this time [Dex IdP](https://dexidp.io) is used for all the
services and a connector must be configured to provide authentication.

!!! warning Dex IdP Configuration Issue
    Unfortunately we need to use the domain ID (UUID) and not the domain name in the
    Dex configuration. This is not known before hand. So at this time you must copy
    the `config.connectors` section from `values-generic.yaml` or `values-azure.yaml`
    into `${DEPLOY_NAME}/helm-configs/dexidp.yaml` and change the value of the
    `domain` key in the `keystone_internal` section to the UUID of the `operator`
    domain.

## User Authentication

### Azure OIDC

To use Azure OIDC support you must first create an Azure Entra Application Registration
and configure it for OIDC authentication.

#### Azure App Registration

1. From the `Azure Entra` > `App registrations` menu, choose `New registration`.
2. Enter a Name for the application (e.g. Undercloud).
3. Specify who can use the application (e.g. Accounts in this organizational directory only).
4. Enter Redirect URI as follows (making sure to replace `${DNS_ZONE}`), then choose Add.
   Platform: Web
   Redirect URI: `https://dex.${DNS_ZONE}/callback`

You will then make a note of the following pieces of information for your application:

- Application ID or Client ID (same value, two different names) we'll call this `{client_id}`.
- Directory ID or Tenant ID (same value, two different names) we'll call this `{tenant_id}`.

#### Azure App Secret

1. From the `Certificates & secrets` menu, choose `New client secret`
2. Enter a Name for the secret (e.g. Undercloud-SSO).
3. Copy and save this value and we'll use it for the `{client_secret}`.

#### Azure Dex Configuration

In `${DEPLOY_NAME}/helm-configs/dexidp.yaml` under the `valuesFiles` key
add `$values/components/dexidp/values-azure.yaml` beneath  `values-generic.yaml`
like:

```yaml title="${DEPLOY_NAME}/helm-configs/dexidp.yaml"
spec:
  sources:
    - chart: dex
      # context omitted
      helm:
        # context omitted
        valuesFiles:
            - $understack/components/dexidp/values-generic.yaml
            - $understack/components/dexidp/values-azure.yaml
            - $deploy/YOUR_CLUSTER/helm-configs/dexidp.yaml
# rest omitted
```

Then create a secret like:

```bash
kubectl --namespace dex \
    create secret generic oidc-sso --dry-run=client \
    --from-literal=issuer=https://login.microsoftonline.com/{tenant_id}/v2.0 \
    --from-literal=client-id={client_id} \
    --from-literal=client-secret={client_secret} \
    --from-literal=redirect-uri=https://dex.${DNS_ZONE}/callback \
    -o yaml > ${UC_DEPLOY}/${DEPLOY_NAME}/secrets/secret-oidc-sso-dex.yaml
```

You must remember to add this secret to your secret storage (e.g. for
Kube Seal you must commit the sealed file to your `${UC_DEPLOY}` repo).

### Static Users

Users can be created in OpenStack Keystone in the `operator` domain for
testing purposes.

## User Authorization

Once users can authenticate to the system, they must be granted authorization
to different parts of the system. The default groups through the system are:

- ucadmin - administrator of the system
- dctech - DC Tech with access to physical systems
- neteng - Network Engineer with access to IPAM and Network configuration
- user - consumer of resources and hardware provided by the system

### Nautobot

To customize the administrator group set the following in your
`${DEPLOY_NAME}/helm-configs/nautobot.yaml`

```yaml title="${DEPLOY_NAME}/helm-configs/nautobot.yaml"
nautobot:
  extraEnvVars:
    # ignoring existing values here, don't remove
    - name: DEX_SUPERUSER_GROUPS
      value: your-admin-group
```
