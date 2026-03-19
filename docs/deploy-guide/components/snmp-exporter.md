# snmp-exporter

SNMP exporter installation.

## Deployment Scope

- Cluster scope: site
- Values key: `site.snmp_exporter`
- ArgoCD Application template: `charts/argocd-understack/templates/application-snmp-exporter.yaml`

## How ArgoCD Builds It

- ArgoCD renders Helm chart `prometheus-snmp-exporter`.
- The deploy repo contributes `prometheus-snmp-exporter/values.yaml` for this component.
- The current template does not apply a deploy-repo overlay directory for this component.

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
site:
  snmp_exporter:
    enabled: true
```

## Deployment Repo Content

Use any secret delivery mechanism you prefer. The contract that matters is the final Kubernetes Secret or manifest shape described below.

Required or commonly required items:

- `values.yaml`: Provide exporter modules, scrape settings, and auth references in `$CLUSTER_NAME/prometheus-snmp-exporter/values.yaml`.

Optional additions:

- `SNMP credential Secret`: If your values reference per-target authentication material, create the Secret name referenced by the chart and populate it with the keys expected by your auth configuration.
