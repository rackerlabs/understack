---
charts:
- octavia
kustomize_paths:
- components/octavia/
argocd_extra:
- The shared site-level `secret-openstack.yaml` and optional `images-openstack.yaml`
  files are loaded before the service-specific values file.
deploy_overrides:
  helm:
    mode: values
  kustomize:
    mode: second_source
---

# octavia

OpenStack Load Balancing service.

## Deployment Scope

- Cluster scope: site
- Values key: `site.octavia`
- ArgoCD Application template: `charts/argocd-understack/templates/application-openstack-helm.yaml`

## How to Enable

Set this component to enabled in your deployment values file:

```yaml title="$CLUSTER_NAME/deploy.yaml"
site:
  octavia:
    enabled: true
```

## How ArgoCD Builds It

{{ component_argocd_builds() }}

## Deployment Repo Content

{{ secrets_disclaimer }}

Required or commonly required items:

- `values.yaml`: Provide the Octavia-specific chart or manifest values.
- `octavia-db-password` Secret: Provide `username` and `password` for the Octavia database user.
- `octavia-rabbitmq-password` Secret: Provide `username` and `password` for the messaging user Octavia should use.

Optional additions:

- `octavia-tls-public` Secret: Provide `tls.crt` and `tls.key` when the public endpoint is exposed with TLS.
- `Extra manifests`: Add provider-network, certificate, or post-deploy supporting resources if the base component is not sufficient.

## Notes

- This service is rendered by `application-openstack-helm.yaml`, which also reads the shared site-level `secret-openstack.yaml` and optional `images-openstack.yaml` files before it reads `octavia/values.yaml`.
