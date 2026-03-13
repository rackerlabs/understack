# mariadb-operator

MariaDB operator installation.

## Deployment Scope

- Cluster scope: site
- Values key: `site.mariadb_operator`
- ArgoCD Application template: `charts/argocd-understack/templates/application-mariadb-operator.yaml`

## How ArgoCD Builds It

- ArgoCD renders Kustomize path `operators/mariadb-operator`.
- The current template does not read a deploy-repo `values.yaml` for this component.
- The current template does not apply a deploy-repo overlay directory for this component.

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
site:
  mariadb_operator:
    enabled: true
```

## Notes

- The current ArgoCD template deploys the shared operator manifests directly and does not consume deploy-repo values or overlay manifests for this component.
- Put database instance configuration in the components that own those databases rather than in this operator page.
