---
charts:
- cinder
kustomize_paths:
- components/cinder/
argocd_extra:
- The shared site-level `secret-openstack.yaml` and optional `images-openstack.yaml`
  files are loaded before the service-specific values file.
deploy_overrides:
  helm:
    mode: values
  kustomize:
    mode: second_source
---

# cinder

OpenStack Block Storage service.

## Deployment Scope

- Cluster scope: site
- Values key: `site.cinder`
- ArgoCD Application template: `charts/argocd-understack/templates/application-openstack-helm.yaml`

## How to Enable

Set this component to enabled in your deployment values file:

```yaml title="$CLUSTER_NAME/deploy.yaml"
site:
  cinder:
    enabled: true
```

## How ArgoCD Builds It

{{ component_argocd_builds() }}

## Deployment Repo Content

{{ secrets_disclaimer }}

Required or commonly required items:

- `values.yaml`: Provide the Cinder-specific chart or manifest values.
- `cinder-db-password` Secret: Provide `username` and `password` for the Cinder database user.
- `cinder-rabbitmq-password` Secret: Provide `username` and `password` for the messaging user Cinder should use.

Optional additions:

- `cinder-netapp-config` Secret: Provide the backend-specific keys required by the NetApp configuration when that backend is enabled.
- `Extra manifests`: Add storage-backend or policy resources if the base chart is not sufficient.

## Notes

- This service is rendered by `application-openstack-helm.yaml`, which also reads the shared site-level `secret-openstack.yaml` and optional `images-openstack.yaml` files before it reads `cinder/values.yaml`.
