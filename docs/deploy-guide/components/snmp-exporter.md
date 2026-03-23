---
charts:
- prometheus-snmp-exporter
deploy_overrides:
  helm:
    mode: values_files
    paths:
    - prometheus-snmp-exporter/values.yaml
  kustomize:
    mode: none
---

# snmp-exporter

SNMP exporter installation.

## Deployment Scope

- Cluster scope: site
- Values key: `site.snmp_exporter`
- ArgoCD Application template: `charts/argocd-understack/templates/application-snmp-exporter.yaml`

## How ArgoCD Builds It

{{ component_argocd_builds() }}

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
site:
  snmp_exporter:
    enabled: true
```

## Deployment Repo Content

{{ secrets_disclaimer }}

Required or commonly required items:

- `values.yaml`: Provide exporter modules, scrape settings, and auth references in `$CLUSTER_NAME/prometheus-snmp-exporter/values.yaml`.

Optional additions:

- `SNMP credential Secret`: If your values reference per-target authentication material, create the Secret name referenced by the chart and populate it with the keys expected by your auth configuration.
