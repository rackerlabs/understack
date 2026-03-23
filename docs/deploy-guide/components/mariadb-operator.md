---
kustomize_paths:
- operators/mariadb-operator
deploy_overrides:
  helm:
    mode: none
  kustomize:
    mode: none
---

# mariadb-operator

MariaDB operator installation.

## Deployment Scope

- Cluster scope: site
- Values key: `site.mariadb_operator`
- ArgoCD Application template: `charts/argocd-understack/templates/application-mariadb-operator.yaml`

## How ArgoCD Builds It

{{ component_argocd_builds() }}

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
site:
  mariadb_operator:
    enabled: true
```

## Deployment Repo Content

{{ secrets_disclaimer }}

Required or commonly required items:

- None for this Application today. It deploys the shared operator manifests directly and does not consume deploy-repo values or overlay manifests for this component.

Optional additions:

- Put database instance configuration in the components that own those databases rather than on this operator page.
