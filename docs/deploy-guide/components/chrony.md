---
kustomize_paths:
- components/chrony
deploy_overrides:
  helm:
    mode: none
  kustomize:
    mode: none
---

# chrony

Chrony integration for OpenStack nodes.

## Deployment Scope

- Cluster scope: site
- Values key: `site.chrony`
- ArgoCD Application template: `charts/argocd-understack/templates/application-chrony.yaml`

## How ArgoCD Builds It

{{ component_argocd_builds() }}

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
site:
  chrony:
    enabled: true
```

## Deployment Repo Content

{{ secrets_disclaimer }}

Required or commonly required items:

- None for this Application today. It deploys the shared `components/chrony` base directly and does not consume deploy-repo values or overlay manifests for this component.

Optional additions:

- Document site-specific time-server configuration with the inventory or host provisioning content that consumes Chrony rather than on this Application page.
