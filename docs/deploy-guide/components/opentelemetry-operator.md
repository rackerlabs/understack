---
charts:
- opentelemetry-operator
kustomize_paths:
- operators/opentelemetry-operator
deploy_overrides:
  helm:
    mode: values
  kustomize:
    mode: none
---

# opentelemetry-operator

OpenTelemetry operator installation.

## Deployment Scope

- Cluster scope: global or site
- Values keys: `global.opentelemetry_operator`, `site.opentelemetry_operator`
- ArgoCD Application template: `charts/argocd-understack/templates/application-opentelemetry-operator.yaml`

## How ArgoCD Builds It

{{ component_argocd_builds() }}

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
global:
  opentelemetry_operator:
    enabled: true
site:
  opentelemetry_operator:
    enabled: true
```

## Deployment Repo Content

{{ secrets_disclaimer }}

Required or commonly required items:

- `values.yaml`: Provide operator chart values if you need to tune admission webhooks, collector image defaults, or related behavior.

## Notes

- The current ArgoCD template reads deploy-repo values for this component but does not apply deploy overlay manifests.
