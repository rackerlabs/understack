# openstack-exporter

Prometheus exporter for OpenStack APIs.

## Deployment Scope

- Cluster scope: site
- Values key: `site.openstack_exporter`
- ArgoCD Application template: `charts/argocd-understack/templates/application-openstack-exporter.yaml`

## How ArgoCD Builds It

- ArgoCD renders Helm chart `prometheus-openstack-exporter`.
- The deploy repo contributes `values.yaml` for this component.
- The current template does not apply a deploy-repo overlay directory for this component.

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
site:
  openstack_exporter:
    enabled: true
```

## Deployment Repo Content

Use any secret delivery mechanism you prefer. The contract that matters is the final Kubernetes Secret or manifest shape described below.

Required or commonly required items:

- `values.yaml`: Provide the exporter endpoint, auth, and scrape settings that are specific to your environment.

## Notes

- The current ArgoCD template consumes deploy-repo values for this component but does not apply an overlay directory. Put component-specific settings in `values.yaml`.
