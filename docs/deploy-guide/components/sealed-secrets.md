---
kustomize_paths:
- bootstrap/sealed-secrets
deploy_overrides:
  helm:
    mode: none
  kustomize:
    mode: none
---

# sealed-secrets

Sealed Secrets controller installation.

## Deployment Scope

- Cluster scope: global or site
- Values keys: `global.sealed_secrets`, `site.sealed_secrets`
- ArgoCD Application template: `charts/argocd-understack/templates/application-sealed-secrets.yaml`

## How ArgoCD Builds It

{{ component_argocd_builds() }}

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
global:
  sealed_secrets:
    enabled: true
site:
  sealed_secrets:
    enabled: true
```

## Deployment Repo Content

{{ secrets_disclaimer }}

Required or commonly required items:

- None for this Application today. It deploys the shared bootstrap manifests directly and does not consume deploy-repo values or overlay manifests for this component.

Optional additions:

- Document individual decrypted Secret shapes on the component pages that consume them rather than here.
