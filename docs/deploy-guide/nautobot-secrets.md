# Manage Nautobot API Token Secrets

This guide documents the current Nautobot token workflow in UnderStack.
Use the `nautobot-api-tokens` chart to reconcile Nautobot users and API tokens from Kubernetes `Secret` objects.

## Overview

`nautobot-api-tokens` is deployed by Argo CD into the `nautobot` namespace. During sync, it creates:

- one PostSync `Job` per configured token in `tokens[]`
- one cleanup PostSync `Job` that removes stale managed tokens

Each job runs `nautobot-server shell --interface python` inside the Nautobot image and reconciles the target Nautobot user and token directly.

## How It Works

1. Create or sync a Kubernetes `Secret` in the `nautobot` namespace with the desired username, email, and API token.
2. Reference that secret from `nautobot-api-tokens/values.yaml` in your deploy repo.
3. Argo CD syncs the `nautobot-api-tokens` Application.
4. The chart runs a PostSync job for each configured entry in `tokens[]`.
5. Each job creates or updates the Nautobot user, enforces an unusable password for API-only access, ensures group membership, and creates or updates the API token.
6. The cleanup job removes previously managed tokens that are no longer listed in `tokens[]`. It can also delete managed users when no desired managed tokens remain.

No `Argo Events`, sensor, label trigger, or Ansible playbook is involved in this workflow.

## Source Secret Requirements

The referenced source secret must exist in the `nautobot` namespace because the reconciliation jobs run there and use `secretKeyRef`.

By default, each token entry expects these keys in the source secret:

| Key | Required | Purpose |
|-----|----------|---------|
| `username` | yes | Nautobot username to manage |
| `email` | yes | Nautobot email for that user |
| `apiToken` | yes | Nautobot API token value to enforce |

You can override the key names per token with `sourceSecretRef.keys`.

Example `ExternalSecret` that renders the expected keys:

```yaml
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: nautobot-token-openstack
  namespace: nautobot
spec:
  refreshInterval: 1h
  secretStoreRef:
    kind: SecretStore
    name: my-secret-backend
  target:
    name: nautobot-token-openstack
    creationPolicy: Owner
    template:
      engineVersion: v2
      type: Opaque
      data:
        username: "&#123;&#123; .username &#125;&#125;"
        email: "&#123;&#123; .email &#125;&#125;"
        apiToken: "&#123;&#123; index (.password | fromJson) \"token\" &#125;&#125;"
  dataFrom:
    - extract:
        key: "12345"
```

The source system can still be Vault, AKV, PasswordSafe, or another backend. The chart only cares about the final Kubernetes `Secret`.

## Prerequisites

- Nautobot is deployed and healthy in the cluster.
- `global.nautobot_api_tokens.enabled` is set to `true`.
- The Argo CD Application template `charts/argocd-understack/templates/application-nautobot-api-tokens.yaml` is enabled for the cluster.
- Required Nautobot runtime config is available to the job pods.
  By default this chart expects:
    - `ConfigMap` `nautobot-env`
    - `Secret` `nautobot-env`
    - `Secret` `nautobot-custom-env`
    - `Secret` key `nautobot-env/NAUTOBOT_DB_PASSWORD`

If your deployment uses different names, override them in the chart values.

## Argo CD Deployment

Enable the component in your cluster deploy file:

```yaml title="$CLUSTER_NAME/deploy.yaml"
global:
  nautobot_api_tokens:
    enabled: true
```

Provide chart values in the deploy repo at:

```text
$CLUSTER_NAME/nautobot-api-tokens/values.yaml
```

The Argo CD Application reads that file from:

```text
charts/argocd-understack/templates/application-nautobot-api-tokens.yaml
```

## Example Values

```yaml
image:
  repository: ghcr.io/nautobot/nautobot
  tag: "3.0.7"
  pullPolicy: IfNotPresent

serviceAccountName: nautobot

nautobot:
  configPath: ""
  dbPasswordSecretRef:
    name: nautobot-env
    key: NAUTOBOT_DB_PASSWORD
  envFromConfigMaps:
    - nautobot-env
  envFromSecrets:
    - nautobot-env
    - nautobot-custom-env

cleanup:
  groupName: nautobot-api-token-managed
  deleteUserWhenNoManagedTokens: true

tokens:
  - name: openstack
    sourceSecretRef:
      name: nautobot-token-openstack
      keys:
        username: username
        email: email
        apiToken: apiToken
    user:
      isSuperuser: false

  - name: workflow
    sourceSecretRef:
      name: nautobot-token-workflow
```

## Reconciliation Behavior

For each enabled entry in `tokens[]`, the chart:

- creates the Nautobot user if it does not exist
- updates email and `isSuperuser` when configured
- enforces an unusable password for managed users
- ensures the user is a member of `cleanup.groupName`
- creates the Nautobot token if it does not exist
- updates the token key if the desired value changes

Managed tokens are marked with the description prefix `nautobot-api-token-managed:` so the cleanup job can identify them safely.

## Validation

After syncing Argo CD:

- confirm the `nautobot-api-tokens` Application synced successfully
- confirm the PostSync jobs in the `nautobot` namespace completed successfully
- confirm the expected user and token exist in Nautobot

If a job fails, check:

- the referenced source secret exists in `nautobot`
- the secret contains the expected keys
- `NAUTOBOT_DB_PASSWORD` is available from `nautobot.dbPasswordSecretRef`
- `nautobot-env` and `nautobot-custom-env` references match your deployment

## References

- `charts/nautobot-api-tokens`
- `charts/argocd-understack/templates/application-nautobot-api-tokens.yaml`
- `docs/deploy-guide/components/nautobot-api-tokens.md`
