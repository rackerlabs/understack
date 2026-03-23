---
kustomize_paths:
- operators/openstack-resource-controller
deploy_overrides:
  helm:
    mode: none
  kustomize:
    mode: none
---

# openstack-resource-controller

OpenStack resource controller operator installation.

## Deployment Scope

- Cluster scope: global or site
- Values keys: `global.openstack_resource_controller`, `site.openstack_resource_controller`
- ArgoCD Application template: `charts/argocd-understack/templates/application-openstack-resource-controller.yaml`

## How ArgoCD Builds It

{{ component_argocd_builds() }}

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

{{ secrets_disclaimer }}

Required or commonly required items:

- None for this Application today. It deploys the shared operator manifests directly and does not consume deploy-repo values or overlay manifests for this component.

Optional additions:

- Document any per-resource credentials or sync rules with the consuming OpenStack component instead of on this operator page.
