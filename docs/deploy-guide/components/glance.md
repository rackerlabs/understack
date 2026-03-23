---
charts:
- glance
kustomize_paths:
- components/glance/
argocd_extra:
- The shared site-level `secret-openstack.yaml` and optional `images-openstack.yaml`
  files are loaded before the service-specific values file.
deploy_overrides:
  helm:
    mode: values
  kustomize:
    mode: second_source
---

# glance

Glance service overlays for a site OpenStack Helm deployment.

## Deployment Scope

- Cluster scope: site
- Values key: `site.glance`
- ArgoCD Application template: `charts/argocd-understack/templates/application-openstack-helm.yaml`

## How ArgoCD Builds It

{{ component_argocd_builds() }}

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
site:
  glance:
    enabled: true
```

## Deployment Repo Content

{{ secrets_disclaimer }}

Required or commonly required items:

- `values.yaml`: Provide the Glance-specific chart values.
- `glance-db-password` Secret: Provide `username` and `password` for the Glance database user.
- `glance-rabbitmq-password` Secret: Provide `username` and `password` for the messaging user Glance should use.

Optional additions:

- `Extra manifests`: Add site-specific storage, policy, or network resources if the base chart is not sufficient.

## Notes

- This service is rendered by `application-openstack-helm.yaml`, which also reads the shared site-level `secret-openstack.yaml` and optional `images-openstack.yaml` files before it reads `glance/values.yaml`.
