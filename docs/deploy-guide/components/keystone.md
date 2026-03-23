---
charts:
- keystone
kustomize_paths:
- components/keystone/
argocd_extra:
- The shared site-level `secret-openstack.yaml` and optional `images-openstack.yaml`
  files are loaded before the service-specific values file.
deploy_overrides:
  helm:
    mode: values
  kustomize:
    mode: second_source
---

# keystone

OpenStack Identity service.

## Deployment Scope

- Cluster scope: site
- Values key: `site.keystone`
- ArgoCD Application template: `charts/argocd-understack/templates/application-openstack-helm.yaml`

## How to Enable

Set this component to enabled in your deployment values file:

```yaml title="$CLUSTER_NAME/deploy.yaml"
site:
  keystone:
    enabled: true
```

## How ArgoCD Builds It

{{ component_argocd_builds() }}

## Deployment Repo Content

{{ secrets_disclaimer }}

Required or commonly required items:

- `values.yaml`: Provide the Keystone-specific chart or manifest values.
- `keystone-admin` Secret: Provide `password` for the admin or bootstrap account.
- `keystone-db-password` Secret: Provide `username` and `password` for the Keystone database user.
- `keystone-rabbitmq-password` Secret: Provide `username` and `password` for the messaging user Keystone should use.

Optional additions:

- `keystone-sso` Secret: Provide `client-id`, `client-secret`, and `issuer` when Keystone uses OIDC or web SSO.
- `sso-passphrase` Secret: Provide the passphrase consumed by the SSO configuration when that flow is enabled.

## Notes

- This service is rendered by `application-openstack-helm.yaml`, which also reads the shared site-level `secret-openstack.yaml` and optional `images-openstack.yaml` files before it reads `keystone/values.yaml`.
