# opentelemetry-operator

OpenTelemetry operator installation.

## Deployment Scope

- Cluster scope: global or site
- Values keys: `global.opentelemetry_operator`, `site.opentelemetry_operator`
- ArgoCD Application template: `charts/argocd-understack/templates/application-opentelemetry-operator.yaml`

## How ArgoCD Builds It

- ArgoCD renders Helm chart `opentelemetry-operator`, Kustomize path `operators/opentelemetry-operator`.
- The deploy repo contributes `values.yaml` for this component.
- The current template does not apply a deploy-repo overlay directory for this component.

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

Use any secret delivery mechanism you prefer. The contract that matters is the final Kubernetes Secret or manifest shape described below.

Required or commonly required items:

- `values.yaml`: Provide operator chart values if you need to tune admission webhooks, collector image defaults, or related behavior.

## Notes

- The current ArgoCD template reads deploy-repo values for this component but does not apply deploy overlay manifests.
