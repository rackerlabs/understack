# cnpg-system

CloudNativePG operator installation.

## Deployment Scope

- Cluster scope: global
- Values key: `global.cnpg_system`
- ArgoCD Application template: `charts/argocd-understack/templates/application-cnpg-system.yaml`

## How ArgoCD Builds It

- ArgoCD renders Kustomize path `operators/cnpg-system`.
- The current template does not read a deploy-repo `values.yaml` for this component.
- The current template does not apply a deploy-repo overlay directory for this component.

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
global:
  cnpg_system:
    enabled: true
```

## Notes

- The current ArgoCD template deploys the operator manifests directly and does not consume deploy-repo values or overlay manifests for this component.
- Create database clusters and backup configuration in the components that own those databases, such as `nautobot`.
