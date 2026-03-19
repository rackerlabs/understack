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

- ArgoCD renders Helm chart `octavia`, Kustomize path `components/octavia/`.
- The shared site-level `secret-openstack.yaml` and optional `images-openstack.yaml` files are loaded before the service-specific values file.
- The deploy repo contributes `values.yaml` for this component.
- The deploy repo overlay directory for this component is applied as a second source, so `kustomization.yaml` and any referenced manifests are part of the final Application.

## Deployment Repo Content

Use any secret delivery mechanism you prefer. The contract that matters is the final Kubernetes Secret or manifest shape described below.

Required or commonly required items:

- `values.yaml`: Provide the Octavia-specific chart or manifest values.
- `octavia-db-password` Secret: Provide `username` and `password` for the Octavia database user.
- `octavia-rabbitmq-password` Secret: Provide `username` and `password` for the messaging user Octavia should use.

Optional additions:

- `octavia-tls-public` Secret: Provide `tls.crt` and `tls.key` when the public endpoint is exposed with TLS.
- `Extra manifests`: Add provider-network, certificate, or post-deploy supporting resources if the base component is not sufficient.

## Notes

- This service is rendered by `application-openstack-helm.yaml`, which also reads the shared site-level `secret-openstack.yaml` and optional `images-openstack.yaml` files before it reads `octavia/values.yaml`.
