---
charts:
- rook-ceph-cluster
kustomize_paths:
- operators/rook
deploy_overrides:
  helm:
    mode: values_files
    paths:
    - rook-ceph-cluster/values.yaml
  kustomize:
    mode: none
---

# rook-ceph-cluster

Rook Ceph cluster installation (split from the combined rook component).

## Deployment Scope

- Cluster scope: global or site
- Values keys: `global.rook_ceph_cluster`, `site.rook_ceph_cluster`
- ArgoCD Application template: `charts/argocd-understack/templates/application-rook-ceph-cluster.yaml`
- Sync wave: `1` (deploys after rook-ceph-operator)

## How ArgoCD Builds It

{{ component_argocd_builds() }}

## How to Enable

Enable this component by setting one or both options under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
global:
  rook_ceph_cluster:
    installApp: true
site:
  rook_ceph_cluster:
    installApp: true
```

### Options

| Key | Default | Description |
|-----|---------|-------------|
| `installApp` | `false` | Deploy the rook-ceph-cluster Helm chart |
| `installConfigs` | `false` | Deploy site-specific Rook cluster configs from the deploy repo |

Typical deployment patterns:

- **Per-site clusters**: Deploy clusters per-site with global operator
- **Global cluster**: Single cluster for development/testing environments

```yaml title="$CLUSTER_NAME/deploy.yaml"
# Per-site clusters with global operator
global:
  rook_ceph_cluster:
    installApp: false
    installConfigs: false
site:
  rook_ceph_cluster:
    installApp: true
    installConfigs: true
```

## Deployment Repo Content

{{ secrets_disclaimer }}

When `installConfigs: true`, the Application reads from:

```text
$DEPLOY_REPO/<cluster-name>/rook-ceph-cluster/
```

Required or commonly required items:

- `rook-ceph-cluster/values.yaml`: Provide cluster topology, storage devices, pools, object stores, and CSI settings.

Optional additions:

- `Storage credential or class resources`: If your values reference Secrets, StorageClasses, CephObjectStores, or similar supporting resources, materialize those final resources with whatever workflow you prefer.
- Additional cluster configuration resources can be placed in the `rook-ceph-cluster/` deploy-repo path when `installConfigs: true`.

## Important Notes

- **Data Protection**: Auto-prune is disabled (`prune: false`) to prevent accidental deletion of storage cluster resources and potential data loss.
- **Deployment Order**: This component has sync wave `1` and requires `rook-ceph-operator` (sync wave `0`) to be deployed first.
- **Prerequisites**: Requires the Rook Ceph operator to be installed and running before cluster deployment.
- **Namespace**: Uses the `rook-ceph` namespace created by the operator component.
