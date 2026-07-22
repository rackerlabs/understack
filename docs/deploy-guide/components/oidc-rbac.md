---
kustomize_paths:
- components/oidc-rbac
deploy_overrides:
  helm:
    mode: none
  kustomize:
    mode: none
---

# oidc-rbac

OIDC RBAC configuration for Kubernetes service account issuer discovery.

## Deployment Scope

- Cluster scope: global, site
- Values key: `global.oidc_rbac`, `site.oidc_rbac`
- ArgoCD Application template: `charts/argocd-understack/templates/application-oidc-rbac.yaml`

## How ArgoCD Builds It

{{ component_argocd_builds() }}

## How to Enable

This component is enabled by default. To disable it:

```yaml title="$CLUSTER_NAME/deploy.yaml"
global:
  oidc_rbac:
    enabled: false
site:
  oidc_rbac:
    enabled: false
```

## Deployment Repo Content

{{ secrets_disclaimer }}

Required or commonly required items:

- None for this Application today. It deploys the shared `components/oidc-rbac` base directly and does not consume deploy-repo values or overlay manifests.
