# nautobot

Global Nautobot deployment and its optional supporting resources.

## Deployment Scope

- Cluster scope: global
- Values key: `global.nautobot`
- ArgoCD Application template: `charts/argocd-understack/templates/application-nautobot.yaml`
- UnderStack wrapper chart: `charts/nautobot-understack`

## How ArgoCD Builds It

- ArgoCD renders the UnderStack wrapper chart `charts/nautobot-understack`, which pulls in the upstream Nautobot Helm chart as a dependency.
- The wrapper chart owns the shared Nautobot deployment contract, including CNPG, SSO config, and post-deploy resources.
- The deploy repo contributes `nautobot/values.yaml` for site-specific overrides.
- The deploy repo overlay directory for this component is still applied as a second source, so `kustomization.yaml` and any referenced manifests remain available for secrets and truly site-owned extras.

## Values and Schema

- Wrapper chart values file: `charts/nautobot-understack/values.yaml`
- Wrapper chart schema: `charts/nautobot-understack/values.schema.json`
- Published schema URL: `https://rackerlabs.github.io/understack/schema/charts/nautobot-understack/values.schema.json`

The values contract is split into two parts:

- `nautobot.*`: pass-through values for the upstream Nautobot chart
- `understack.nautobot.*`: UnderStack-managed resources and behavior such as CNPG, SSO, backups, and the post-deploy job

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
global:
  nautobot:
    enabled: true
```

## Deployment Repo Content

Use any secret delivery mechanism you prefer. The contract that matters is the final Kubernetes Secret or manifest shape described below.

Required or commonly required items:

- `values.yaml`: Provide Nautobot runtime settings and site-specific overrides for the wrapper chart. Use `nautobot.*` for upstream Nautobot settings and `understack.nautobot.*` for UnderStack-managed resources.
- `nautobot-django` Secret: Provide a `NAUTOBOT_SECRET_KEY` value.
- `nautobot-redis` Secret: Provide a `NAUTOBOT_REDIS_PASSWORD` value.
- `nautobot-superuser` Secret: Provide `username`, `password`, `email`, and `apitoken` for the initial administrative account.

Optional additions:

- `nautobot-sso` Secret or `ExternalSecret`: Provide `client-id`, `client-secret`, and `issuer` when Nautobot authenticates through an external identity provider.
- `aws-s3-backup` Secret: Provide `access-key-id` and `secret-access-key` when scheduled backups are pushed to object storage.
- `dockerconfigjson-github-com` Secret: Provide `.dockerconfigjson` if Nautobot images or plugins come from a private registry.
- `nautobot-custom-env` Secret: Add any extra environment variables the deployment should inject into Nautobot, such as integration credentials or DSNs.
- `Catalog and bootstrap content`: Add app definitions, device types, location types, locations, rack groups, or racks if you want Nautobot preloaded with inventory metadata.

## What the Wrapper Chart Owns

The wrapper chart is the preferred place for shared Nautobot platform resources that need templating or site-level configuration:

- CloudNativePG `Cluster` and `ScheduledBackup`
- Nautobot SSO `ConfigMap`
- Nautobot SSO `ExternalSecret`
- Nautobot post-deploy `Job`

Prefer configuring these through `nautobot/values.yaml` instead of replacing full manifests in the deploy repo.

## What Should Stay in the Deploy Repo

Keep deploy-repo content focused on inputs and site-owned resources:

- Secrets and `ExternalSecret` definitions
- Inventory and bootstrap data
- Device type catalogs
- One-off local integrations or adjunct resources that are not part of the shared Nautobot deployment contract
