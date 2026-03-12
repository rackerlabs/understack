# openstack-resource-controller

OpenStack Resource Controller operator.

## Deployment Scope

- Cluster scope: global, site
- Values key: `global.openstack_resource_controller / site.openstack_resource_controller`
- ArgoCD Application template: `charts/argocd-understack/templates/application-openstack-resource-controller.yaml`

## How to Enable

Set this component to enabled in your deployment values file:

```yaml title="$CLUSTER_NAME/deploy.yaml"
global:
  openstack_resource_controller:
    enabled: true
```

## Deployment Repo Overrides

Use your deployment repo to provide environment-specific values and overlays.
Start with [Component Reference](../components/index.md) and [Deploy Repo](../deploy-repo.md).

## Notes

- Document prerequisites for this component.
- Document required secrets and config inputs.
- Document validation checks and troubleshooting commands.
