---
charts:
- placement
kustomize_paths:
- components/placement/
argocd_extra:
- The shared site-level `secret-openstack.yaml` and optional `images-openstack.yaml`
  files are loaded before the service-specific values file.
deploy_overrides:
  helm:
    mode: values
  kustomize:
    mode: second_source
---

# placement

Placement service overlays for a site OpenStack Helm deployment.

## Deployment Scope

- Cluster scope: site
- Values key: `site.placement`
- ArgoCD Application template: `charts/argocd-understack/templates/application-openstack-helm.yaml`

## How ArgoCD Builds It

{{ component_argocd_builds() }}

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
site:
  placement:
    enabled: true
```

## Deployment Repo Content

{{ secrets_disclaimer }}

Required or commonly required items:

- `values.yaml`: Provide the Placement-specific chart or manifest values.
- `placement-db-password` Secret: Provide `username` and `password` for the Placement database user.

Optional additions:

- `Extra manifests`: Add service-specific policy or integration resources if they are not already covered by values.

## Notes

- This service is rendered by `application-openstack-helm.yaml`, which also reads the shared site-level `secret-openstack.yaml` and optional `images-openstack.yaml` files before it reads `placement/values.yaml`.
