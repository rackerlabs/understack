---
kustomize_paths:
- operators/external-secrets
deploy_overrides:
  helm:
    mode: none
  kustomize:
    mode: none
---

# external-secrets

External Secrets operator installation.

## Deployment Scope

- Cluster scope: global or site
- Values keys: `global.external_secrets`, `site.external_secrets`
- ArgoCD Application template: `charts/argocd-understack/templates/application-external-secrets.yaml`

## How ArgoCD Builds It

{{ component_argocd_builds() }}

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
global:
  external_secrets:
    enabled: true
site:
  external_secrets:
    enabled: true
```

## Deployment Repo Content

{{ secrets_disclaimer }}

Required or commonly required items:

- None for this Application today. It deploys the shared operator manifests directly and does not read deploy-repo values or overlay manifests for this component.

Optional additions:

- Document provider-specific SecretStores and authentication material only where a consuming component needs the resulting Secret shape.
