---
charts:
- nodedash
deploy_overrides:
  helm:
    mode: values
  kustomize:
    mode: second_source
---

# nodedash

[nodedash](https://github.com/rackerlabs/nodedash) is a web UI for hardware
administration of Ironic bare metal nodes: power, maintenance, inventory, BIOS,
firmware, runbooks and console. Operators sign in through Keystone WebSSO and
pick a region, and nodedash finds that region's Ironic in the Keystone service
catalog, so one deployment serves every site.

## Deployment Scope

- Cluster scope: global
- Values key: `global.nodedash`
- ArgoCD Application template: `charts/argocd-understack/templates/application-nodedash.yaml`

## How ArgoCD Builds It

{{ component_argocd_builds() }}

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
global:
  nodedash:
    enabled: true
```

It deploys into the `nodedash` namespace. Set `global.nodedash.namespace` to
use another, and make sure the `understack` AppProject allows it.

## Deployment Repo Content

{{ secrets_disclaimer }}

Required or commonly required items:

- `values.yaml`: Set the chart's `config`, at least `PUBLIC_URL`, `KEYSTONE_URL`
  and `IDENTITY_PROVIDERS`, and how the page is reached (`httpRoute` or
  `ingress`). See the chart's `values.yaml` for every option.
- Session key Secret: `SESSION_KEYS` encrypts the session cookie that carries
  each user's Keystone tokens. Give each environment its own key, from
  `openssl rand -base64 32`. Either set `sessionKeys.externalSecret` in
  `values.yaml` so the chart creates an ExternalSecret, or provide the Secret
  yourself and name it in `sessionKeys.secretName`.
- `kustomization.yaml`: The directory is also applied as a second source, so
  list any extra manifests here, or `resources: []` when there are none.

Outside this directory, Keystone must list `${PUBLIC_URL}/api/auth/websso` in
its `trusted_dashboard` setting, or WebSSO sign-in is refused.

Optional additions:

- CA bundle: Mount it with `extraVolumes`, `extraVolumeMounts` and
  `NODE_EXTRA_CA_CERTS` in `extraEnv` when Keystone or Ironic use a private CA.
- `networkPolicy`: Restrict ingress to the gateway and egress to Keystone and
  Ironic.
