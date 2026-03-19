# rook

Rook Ceph operator and cluster installation.

## Deployment Scope

- Cluster scope: global or site
- Values keys: `global.rook`, `site.rook`
- ArgoCD Application template: `charts/argocd-understack/templates/application-rook.yaml`

## How ArgoCD Builds It

- ArgoCD renders Helm chart `rook-ceph`, Helm chart `rook-ceph-cluster`, Kustomize path `operators/rook`.
- The deploy repo contributes `rook-operator/values.yaml` and `rook-cluster/values.yaml` for this component.
- The current template does not apply a deploy-repo overlay directory for this component.

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

Use any secret delivery mechanism you prefer. The contract that matters is the final Kubernetes Secret or manifest shape described below.

Required or commonly required items:

- `rook-operator/values.yaml`: Provide operator chart overrides when the shared defaults are not sufficient.
- `rook-cluster/values.yaml`: Provide cluster topology, storage devices, pools, object stores, and CSI settings.

Optional additions:

- `Storage credential or class resources`: If your values reference Secrets, StorageClasses, CephObjectStores, or similar supporting resources, materialize those final resources with whatever workflow you prefer.
