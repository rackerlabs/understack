# monitoring

Prometheus/Grafana monitoring stack.

## Deployment Scope

- Cluster scope: global, site
- Values key: `global.monitoring / site.monitoring`
- ArgoCD Application template: `charts/argocd-understack/templates/application-monitoring.yaml`
- Related template: `charts/argocd-understack/templates/application-prometheus-operator-crds.yaml`

## How to Enable

Set this component to enabled in your deployment values file:

```yaml title="$CLUSTER_NAME/deploy.yaml"
global:
  monitoring:
    enabled: true
```

## Deployment Repo Overrides

Use your deployment repo to provide environment-specific values and overlays.
Start with [Configuring Components](../components/index.md) and [Deploy Repo](../deploy-repo.md).

## Notes

- Document prerequisites for this component.
- Document required secrets and config inputs.
- Document validation checks and troubleshooting commands.
