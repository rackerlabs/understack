---
charts:
- nautobotop
deploy_overrides:
  helm:
    mode: values
  kustomize:
    mode: second_source
---

# nautobotop

Global Nautobot operator deployment driven from the deploy repo.

## Deployment Scope

- Cluster scope: global
- Values key: `global.nautobotop`
- ArgoCD Application template: `charts/argocd-understack/templates/application-nautobotop.yaml`

## How ArgoCD Builds It

{{ component_argocd_builds() }}

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
global:
  nautobotop:
    enabled: true
```

## Deployment Repo Content

{{ secrets_disclaimer }}

Required or commonly required items:

- `values.yaml`: Provide the Helm values for the operator itself.
- `Operator custom resource`: Add the `Nautobot` custom resource that declares the instance the operator should manage.
- `nautobot-token` Secret: Provide `username`, `token`, and `hostname` so the operator or helper jobs can call the source-of-truth API.

Optional additions:

- `Additional operator-managed objects`: Add extra custom resources here if you run more than one operator-managed Nautobot workload.
