# snmp-exporter

SNMP exporter installation.

## Deployment Scope

- Cluster scope: site
- Values key: `site.snmp_exporter`
- ArgoCD Application template: `charts/argocd-understack/templates/application-snmp-exporter.yaml`

## How ArgoCD Builds It

- ArgoCD renders Helm chart `prometheus-snmp-exporter`.
- The current template does not read a deploy-repo `values.yaml` for this component.
- The current template does not apply a deploy-repo overlay directory for this component.

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
site:
  snmp_exporter:
    enabled: true
```

## Notes

- The current ArgoCD template installs the exporter chart directly and does not consume deploy-repo values or overlay manifests for this component.
- If you need site-specific modules or credential Secrets, either document them in the values model used by the chart or update the ArgoCD template to include a deploy overlay.
