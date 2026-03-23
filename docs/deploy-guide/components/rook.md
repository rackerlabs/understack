---
charts:
- rook-ceph
- rook-ceph-cluster
kustomize_paths:
- operators/rook
deploy_overrides:
  helm:
    mode: values_files
    paths:
    - rook-operator/values.yaml
    - rook-cluster/values.yaml
  kustomize:
    mode: none
---

# rook

Rook Ceph operator and cluster installation.

## Deployment Scope

- Cluster scope: global or site
- Values keys: `global.rook`, `site.rook`
- ArgoCD Application template: `charts/argocd-understack/templates/application-rook.yaml`

## How ArgoCD Builds It

{{ component_argocd_builds() }}

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
global:
  rook:
    enabled: true
site:
  rook:
    enabled: true
```

## Deployment Repo Content

{{ secrets_disclaimer }}

Required or commonly required items:

- `rook-operator/values.yaml`: Provide operator chart overrides when the shared defaults are not sufficient.
- `rook-cluster/values.yaml`: Provide cluster topology, storage devices, pools, object stores, and CSI settings.

Optional additions:

- `Storage credential or class resources`: If your values reference Secrets, StorageClasses, CephObjectStores, or similar supporting resources, materialize those final resources with whatever workflow you prefer.
