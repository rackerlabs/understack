---
charts:
- rook-ceph
kustomize_paths:
- operators/rook
deploy_overrides:
  helm:
    mode: values_files
    paths:
    - rook-ceph-operator/values.yaml
  kustomize:
    mode: none
---

# rook-ceph-operator

Rook Ceph operator installation (split from the combined rook component).

## Deployment Scope

- Cluster scope: global or site
- Values keys: `global.rook_ceph_operator`, `site.rook_ceph_operator`
- ArgoCD Application template: `charts/argocd-understack/templates/application-rook-ceph-operator.yaml`
- Sync wave: `0` (deploys before rook-ceph-cluster)

## How ArgoCD Builds It

{{ component_argocd_builds() }}

## How to Enable

Enable this component by setting one or both options under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
global:
  rook_ceph_operator:
    installApp: true
site:
  rook_ceph_operator:
    installApp: true
```

### Options

| Key | Default | Description |
|-----|---------|-------------|
| `installApp` | `false` | Deploy the rook-ceph Helm chart (operator) |
| `installConfigs` | `false` | Deploy site-specific Rook operator configs from the deploy repo |

Typical deployment patterns:

- **Global operator**: Deploy operator globally and clusters per-site
- **Per-site operator**: Deploy both operator and cluster per-site for isolation

```yaml title="$CLUSTER_NAME/deploy.yaml"
# Global operator, site clusters
global:
  rook_ceph_operator:
    installApp: true
    installConfigs: true
site:
  rook_ceph_operator:
    installApp: false
    installConfigs: false
```

## Deployment Repo Content

{{ secrets_disclaimer }}

When `installConfigs: true`, the Application reads from:

```text
$DEPLOY_REPO/<cluster-name>/rook-ceph-operator/
```

Required or commonly required items:

- `rook-ceph-operator/values.yaml`: Provide operator chart overrides when the shared defaults are not sufficient.

Optional additions:

- Additional operator configuration resources can be placed in the `rook-ceph-operator/` deploy-repo path when `installConfigs: true`.

## Important Notes

- **Data Protection**: Auto-prune is disabled (`prune: false`) to prevent accidental deletion of storage operator resources.
- **Deployment Order**: This component has sync wave `0` and should deploy before `rook-ceph-cluster` (sync wave `1`).
- **Namespace Management**: Creates the `rook-ceph` namespace with deletion protection.
