---
charts:
- nautobot
kustomize_paths:
- components/nautobot
deploy_overrides:
  helm:
    mode: values
  kustomize:
    mode: second_source
---

# nautobot

Global Nautobot deployment and its optional supporting resources.

## Deployment Scope

- Cluster scope: global
- Values key: `global.nautobot`
- ArgoCD Application template: `charts/argocd-understack/templates/application-nautobot.yaml`

## How ArgoCD Builds It

{{ component_argocd_builds() }}

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
global:
  nautobot:
    enabled: true
```

## Deployment Repo Content

{{ secrets_disclaimer }}

Required or commonly required items:

- `values.yaml`: Provide Nautobot runtime settings such as ingress, plugins, worker sizing, and feature flags.
- `nautobot-django` Secret: Provide a `NAUTOBOT_SECRET_KEY` value.
- `nautobot-redis` Secret: Provide a `NAUTOBOT_REDIS_PASSWORD` value.
- `nautobot-superuser` Secret: Provide `username`, `password`, `email`, and `apitoken` for the initial administrative account.

Optional additions:

- `nautobot-sso` Secret: Provide `client-id`, `client-secret`, and `issuer` when Nautobot authenticates through an external identity provider.
- `aws-s3-backup` Secret: Provide `access-key-id` and `secret-access-key` when scheduled backups are pushed to object storage.
- `dockerconfigjson-github-com` Secret: Provide `.dockerconfigjson` if Nautobot images or plugins come from a private registry.
- `nautobot-custom-env` Secret: Add any extra environment variables the deployment should inject into Nautobot, such as integration credentials or DSNs.
- `Database cluster and backup manifests`: Add a CloudNativePG cluster, backup schedule, or similar database resources if this deployment owns its own PostgreSQL cluster.
- `Catalog and bootstrap content`: Add app definitions, device types, location types, locations, rack groups, or racks if you want Nautobot preloaded with inventory metadata.
