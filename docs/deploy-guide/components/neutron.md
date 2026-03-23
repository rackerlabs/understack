---
charts:
- neutron
kustomize_paths:
- components/neutron/
argocd_extra:
- The shared site-level `secret-openstack.yaml` and optional `images-openstack.yaml`
  files are loaded before the service-specific values file.
deploy_overrides:
  helm:
    mode: values
  kustomize:
    mode: second_source
---

# neutron

Neutron service overlays for a site OpenStack Helm deployment.

## Deployment Scope

- Cluster scope: site
- Values key: `site.neutron`
- ArgoCD Application template: `charts/argocd-understack/templates/application-openstack-helm.yaml`

## How ArgoCD Builds It

{{ component_argocd_builds() }}

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
site:
  neutron:
    enabled: true
```

## Deployment Repo Content

{{ secrets_disclaimer }}

Required or commonly required items:

- `values.yaml`: Provide the Neutron-specific chart or manifest values.
- `neutron-db-password` Secret: Provide `username` and `password` for the Neutron database user.
- `neutron-rabbitmq-password` Secret: Provide `username` and `password` for the Neutron messaging user.
- `undersync-token` Secret: Provide a `token` value if Neutron automation needs to call undersync.

Optional additions:

- `Extra manifests`: Add network policy, provider-network, or service-specific resources if they are not already covered by values.

## Notes

- This service is rendered by `application-openstack-helm.yaml`, which also reads the shared site-level `secret-openstack.yaml` and optional `images-openstack.yaml` files before it reads `neutron/values.yaml`.
