# snmp-exporter

SNMP exporter for network telemetry.

## Deployment Scope

- Cluster scope: site
- Values key: `site.snmp_exporter`
- ArgoCD Application template: `charts/argocd-understack/templates/application-snmp-exporter.yaml`

## How to Enable

Set this component to enabled in your deployment values file:

```yaml title="$CLUSTER_NAME/deploy.yaml"
site:
  snmp_exporter:
    enabled: true
```

## Deployment Repo Overrides

Use your deployment repo to provide environment-specific values and overlays.
Start with [Configuring Components](../components/index.md) and [Deploy Repo](../deploy-repo.md).

## Notes

- Document prerequisites for this component.
- Document required secrets and config inputs.
- Document validation checks and troubleshooting commands.
