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

- ArgoCD renders Helm chart `keystone`, Kustomize path `components/keystone/`.
- The shared site-level `secret-openstack.yaml` and optional `images-openstack.yaml` files are loaded before the service-specific values file.
- The deploy repo contributes `values.yaml` for this component.
- The deploy repo overlay directory for this component is applied as a second source, so `kustomization.yaml` and any referenced manifests are part of the final Application.

## Deployment Repo Content

Use any secret delivery mechanism you prefer. The contract that matters is the final Kubernetes Secret or manifest shape described below.

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
