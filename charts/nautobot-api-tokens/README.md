# nautobot-api-tokens

Helm chart that manages Nautobot users and API tokens from Kubernetes Secret references.

## Behavior

- Renders one Argo CD hook `Job` per entry in `values.yaml` `tokens[]`.
- Renders one additional Argo CD hook `Job` that cleans up stale managed tokens.
- Each job runs `nautobot-server shell --interface python` using a mounted managed script.
- User and token reconciliation is idempotent:
  - create user if missing
  - update email/password/flags if changed
  - ensure group membership for managed users
  - create token if missing
  - update token key if changed
- Managed tokens are stamped with `Token.description` prefix `nautobot-api-token-managed:`.
- Cleanup job removes managed tokens that are no longer present in `tokens[]`.
- Cleanup job can also delete users in `cleanup.groupName` when they have no desired managed tokens.

## Image behavior

- Default image is upstream Nautobot.
- Default tag comes from chart `appVersion` (currently `3.0.7`).
- You can override image repository/tag/pullPolicy in values.

## Config behavior

- `nautobot.configPath` is optional.
- If set, chart injects `NAUTOBOT_CONFIG`.
- If unset/empty, container default config behavior is used.
- `nautobot.dbPasswordSecretRef` configures the Secret `name`/`key` used to inject `NAUTOBOT_DB_PASSWORD`.

## Example values

```yaml
image:
  repository: ghcr.io/nautobot/nautobot
  tag: "3.0.7"
  pullPolicy: IfNotPresent

nautobot:
  configPath: ""
  dbPasswordSecretRef:
    name: nautobot-env
    key: NAUTOBOT_DB_PASSWORD

cleanup:
  groupName: nautobot-api-token-managed
  deleteUserWhenNoManagedTokens: true

tokens:
  - name: inventory-client
    sourceSecretRef:
      name: nautobot-token-inventory
      keys:
        username: username
        email: email
        password: password
        apiToken: apiToken
    user:
      isSuperuser: false

  - name: automation-client
    sourceSecretRef:
      name: nautobot-token-automation
      keys:
        username: username
        email: email
        password: password
        apiToken: apiToken
```

## Install

```bash
helm upgrade --install nautobot-api-tokens ./charts/nautobot-api-tokens -n nautobot
```
