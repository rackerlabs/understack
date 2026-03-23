---
charts:
- prometheus-openstack-exporter
deploy_overrides:
  helm:
    mode: values
  kustomize:
    mode: none
---

# openstack-exporter

Prometheus exporter for OpenStack APIs.

## Deployment Scope

- Cluster scope: site
- Values key: `site.openstack_exporter`
- ArgoCD Application template: `charts/argocd-understack/templates/application-openstack-exporter.yaml`

## How ArgoCD Builds It

{{ component_argocd_builds() }}

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
site:
  openstack_exporter:
    enabled: true
```

## Deployment Repo Content

{{ secrets_disclaimer }}

Required or commonly required items:

- `values.yaml`: Provide the exporter endpoint, auth, and scrape settings that are specific to your environment.

## Notes

- The current ArgoCD template consumes deploy-repo values for this component but does not apply an overlay directory. Put component-specific settings in `values.yaml`.
