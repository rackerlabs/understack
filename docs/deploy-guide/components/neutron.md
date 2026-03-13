# neutron

Neutron service overlays for a site OpenStack Helm deployment.

## Deployment Scope

- Cluster scope: site
- Values key: `site.neutron`
- ArgoCD Application template: `charts/argocd-understack/templates/application-openstack-helm.yaml`

## How ArgoCD Builds It

- ArgoCD renders Helm chart `neutron`, Kustomize path `components/neutron/`.
- The shared site-level `secret-openstack.yaml` and optional `images-openstack.yaml` files are loaded before the service-specific values file.
- The deploy repo contributes `values.yaml` for this component.
- The deploy repo overlay directory for this component is applied as a second source, so `kustomization.yaml` and any referenced manifests are part of the final Application.

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
site:
  neutron:
    enabled: true
```

## Deployment Repo Content

Use any secret delivery mechanism you prefer. The contract that matters is the final Kubernetes Secret or manifest shape described below.

Required or commonly required items:

- `values.yaml`: Provide the Neutron-specific chart or manifest values.
- `neutron-db-password` Secret: Provide `username` and `password` for the Neutron database user.
- `neutron-rabbitmq-password` Secret: Provide `username` and `password` for the Neutron messaging user.
- `undersync-token` Secret: Provide a `token` value if Neutron automation needs to call undersync.

Optional additions:

- `Extra manifests`: Add network policy, provider-network, or service-specific resources if they are not already covered by values.

## Notes

- This service is rendered by `application-openstack-helm.yaml`, which also reads the shared site-level `secret-openstack.yaml` and optional `images-openstack.yaml` files before it reads `neutron/values.yaml`.
