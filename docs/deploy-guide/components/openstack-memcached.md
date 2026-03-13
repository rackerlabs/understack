# openstack-memcached

Memcached settings for shared OpenStack caching.

## Deployment Scope

- Cluster scope: site
- Values key: `site.openstack_memcached`
- ArgoCD Application template: `charts/argocd-understack/templates/application-openstack-memcached.yaml`

## How ArgoCD Builds It

- ArgoCD renders Helm chart `memcached`.
- The deploy repo contributes `values.yaml` for this component.
- The current template does not apply a deploy-repo overlay directory for this component.

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
site:
  openstack_memcached:
    enabled: true
```

## Deployment Repo Content

Use any secret delivery mechanism you prefer. The contract that matters is the final Kubernetes Secret or manifest shape described below.

Required or commonly required items:

- `values.yaml`: Provide the replica count, resource sizing, and any cache-specific values needed by your environment.

## Notes

- The current ArgoCD template reads deploy-repo values for this component but does not apply deploy overlay manifests.
