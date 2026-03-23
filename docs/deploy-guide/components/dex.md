---
charts:
- dex
kustomize_paths:
- components/dex
deploy_overrides:
  helm:
    mode: values
  kustomize:
    mode: second_source
---

# dex

Dex identity provider configuration and client registrations.

## Deployment Scope

- Cluster scope: global
- Values key: `global.dex`
- ArgoCD Application template: `charts/argocd-understack/templates/application-dex.yaml`

## How ArgoCD Builds It

{{ component_argocd_builds() }}

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
global:
  dex:
    enabled: true
```

## Deployment Repo Content

{{ secrets_disclaimer }}

Required or commonly required items:

- `values.yaml`: Provide the Dex runtime settings that are specific to your identity environment.
- `connector-sso` Secret: Provide the client credentials for the upstream identity connector. The example shape is `client-id`, `client-secret`, and `issuer`.
- `client-*-sso` Secrets: Create one Secret per relying party that should authenticate through Dex. The common key shape is `client-id`, `client-secret`, and `issuer`.

Optional additions:

- `client-localdev-sso` or other local/test client Secrets: Add extra client registrations for development or troubleshooting environments without changing the shared base manifests.
