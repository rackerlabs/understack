---
charts:
- memcached
deploy_overrides:
  helm:
    mode: values
  kustomize:
    mode: none
---

# openstack-memcached

Memcached settings for shared OpenStack caching.

## Deployment Scope

- Cluster scope: site
- Values key: `site.openstack_memcached`
- ArgoCD Application template: `charts/argocd-understack/templates/application-openstack-memcached.yaml`

## How ArgoCD Builds It

{{ component_argocd_builds() }}

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
site:
  openstack_memcached:
    enabled: true
```

## Deployment Repo Content

{{ secrets_disclaimer }}

Required or commonly required items:

- `values.yaml`: Provide the replica count, resource sizing, and any cache-specific values needed by your environment.

## Notes

- The current ArgoCD template reads deploy-repo values for this component but does not apply deploy overlay manifests.
