# rook

Rook Ceph operator and cluster installation.

## Deployment Scope

- Cluster scope: global or site
- Values keys: `global.rook`, `site.rook`
- ArgoCD Application template: `charts/argocd-understack/templates/application-rook.yaml`

## How ArgoCD Builds It

- ArgoCD renders Helm chart `rook-ceph`, Helm chart `rook-ceph-cluster`, Kustomize path `operators/rook`.
- The current template does not read a deploy-repo `values.yaml` for this component.
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

## Notes

- The current ArgoCD template installs the shared charts and operator manifests directly and does not consume deploy-repo values or overlay manifests for this component.
- If you later need site-specific storage overlays, update the ArgoCD template first so the deploy repo is actually part of the rendered Application.
