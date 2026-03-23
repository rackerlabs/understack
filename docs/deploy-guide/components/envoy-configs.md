---
kustomize_paths:
- components/envoy-configs
deploy_overrides:
  helm:
    mode: values
  kustomize:
    mode: second_source
---

# envoy-configs

Envoy configuration overlays applied on top of the shared base resources.

## Deployment Scope

- Cluster scope: global or site
- Values keys: `global.envoy_configs`, `site.envoy_configs`
- ArgoCD Application template: `charts/argocd-understack/templates/application-envoy-configs.yaml`

## How ArgoCD Builds It

{{ component_argocd_builds() }}

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
global:
  envoy_configs:
    enabled: true
site:
  envoy_configs:
    enabled: true
```

## Deployment Repo Content

{{ secrets_disclaimer }}

Required or commonly required items:

- `values.yaml`: Provide the configuration values consumed by the shared Envoy config base.
- `kustomization.yaml`: Add any extra Gateway API, EnvoyPatchPolicy, or ConfigMap resources that your environment requires.

Optional additions:

- No extra manifests are present in the current example overlay, but this directory is wired into ArgoCD and is the right place for site-specific Envoy resources.
