---
charts:
- cert-manager
deploy_overrides:
  helm:
    mode: none
  kustomize:
    mode: none
---

# cert-manager

Certificate management operator installation.

## Deployment Scope

- Cluster scope: global or site
- Values keys: `global.cert_manager`, `site.cert_manager`
- ArgoCD Application template: `charts/argocd-understack/templates/application-cert-manager.yaml`

## How ArgoCD Builds It

{{ component_argocd_builds() }}

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
global:
  cert_manager:
    enabled: true
site:
  cert_manager:
    enabled: true
```

## Deployment Repo Content

{{ secrets_disclaimer }}

Required or commonly required items:

- None for this Application today. It installs the upstream chart with inline values and does not consume deploy-repo `values.yaml` or overlay content.

Optional additions:

- Document issuer manifests and challenge-credential Secrets in the `cluster-issuer` component page rather than here.
