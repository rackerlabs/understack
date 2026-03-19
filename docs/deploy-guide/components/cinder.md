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

- ArgoCD renders Helm chart `cinder`, Kustomize path `components/cinder/`.
- The shared site-level `secret-openstack.yaml` and optional `images-openstack.yaml` files are loaded before the service-specific values file.
- The deploy repo contributes `values.yaml` for this component.
- The deploy repo overlay directory for this component is applied as a second source, so `kustomization.yaml` and any referenced manifests are part of the final Application.

## Deployment Repo Content

Use any secret delivery mechanism you prefer. The contract that matters is the final Kubernetes Secret or manifest shape described below.

Required or commonly required items:

- `values.yaml`: Provide the Cinder-specific chart or manifest values.
- `cinder-db-password` Secret: Provide `username` and `password` for the Cinder database user.
- `cinder-rabbitmq-password` Secret: Provide `username` and `password` for the messaging user Cinder should use.

Optional additions:

- `cinder-netapp-config` Secret: Provide the backend-specific keys required by the NetApp configuration when that backend is enabled.
- `Extra manifests`: Add storage-backend or policy resources if the base chart is not sufficient.

## Notes

- This service is rendered by `application-openstack-helm.yaml`, which also reads the shared site-level `secret-openstack.yaml` and optional `images-openstack.yaml` files before it reads `cinder/values.yaml`.
