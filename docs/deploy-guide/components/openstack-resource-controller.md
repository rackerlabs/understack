# openstack-resource-controller

OpenStack resource controller operator installation.

## Deployment Scope

- Cluster scope: global or site
- Values keys: `global.openstack_resource_controller`, `site.openstack_resource_controller`
- ArgoCD Application template: `charts/argocd-understack/templates/application-openstack-resource-controller.yaml`

## How ArgoCD Builds It

- ArgoCD renders Kustomize path `operators/openstack-resource-controller`.
- The current template does not read a deploy-repo `values.yaml` for this component.
- The current template does not apply a deploy-repo overlay directory for this component.

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
global:
  openstack_resource_controller:
    enabled: true
site:
  openstack_resource_controller:
    enabled: true
```

## Deployment Repo Content

Use any secret delivery mechanism you prefer. The contract that matters is the final Kubernetes Secret or manifest shape described below.

Required or commonly required items:

- None for this Application today. It deploys the shared operator manifests directly and does not consume deploy-repo values or overlay manifests for this component.

Optional additions:

- Document any per-resource credentials or sync rules with the consuming OpenStack component instead of on this operator page.
