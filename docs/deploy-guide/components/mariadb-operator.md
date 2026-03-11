# mariadb-operator

MariaDB operator deployment.

## Deployment Scope

- Cluster scope: site
- Values key: `site.mariadb_operator`
- ArgoCD Application template: `charts/argocd-understack/templates/application-mariadb-operator.yaml`
- Related template: `charts/argocd-understack/templates/application-mariadb-operator-crds.yaml`

## How to Enable

Set this component to enabled in your deployment values file:

```yaml title="$CLUSTER_NAME/deploy.yaml"
site:
  mariadb_operator:
    enabled: true
```

## Deployment Repo Overrides

Use your deployment repo to provide environment-specific values and overlays.
Start with [Component Reference](../components/index.md) and [Deploy Repo](../deploy-repo.md).

## Notes

- Document prerequisites for this component.
- Document required secrets and config inputs.
- Document validation checks and troubleshooting commands.
