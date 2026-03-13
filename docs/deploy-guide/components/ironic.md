# ironic

Ironic control-plane overlays for provisioning services and site networking.

## Deployment Scope

- Cluster scope: site
- Values key: `site.ironic`
- ArgoCD Application template: `charts/argocd-understack/templates/application-openstack-helm.yaml`

## How ArgoCD Builds It

- ArgoCD renders Helm chart `ironic`, Kustomize path `components/ironic/`.
- The shared site-level `secret-openstack.yaml` and optional `images-openstack.yaml` files are loaded before the service-specific values file.
- The deploy repo contributes `values.yaml` for this component.
- The deploy repo overlay directory for this component is applied as a second source, so `kustomization.yaml` and any referenced manifests are part of the final Application.

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
site:
  ironic:
    enabled: true
```

## Deployment Repo Content

Use any secret delivery mechanism you prefer. The contract that matters is the final Kubernetes Secret or manifest shape described below.

Required or commonly required items:

- `values.yaml`: Provide the service values consumed by the base Ironic manifests.
- `ironic-db-password` Secret: Provide `username` and `password` for the Ironic database user.
- `ironic-rabbitmq-password` Secret: Provide `username` and `password` for the Ironic messaging user.
- `dnsmasq ConfigMap`: Provide the provisioning-network settings that dnsmasq needs, typically including DNS and NTP servers, ingress addresses, interface names, DHCP ranges, routes, MTU values, and any per-network tags.
- `LoadBalancer Service manifests`: Create the Services needed to expose the Ironic API, dnsmasq endpoint, and any graphical console endpoints required by your environment.

Optional additions:

- `Additional network or console Services`: Add more Services if your hardware workflow needs extra listener addresses or per-rack console endpoints.

## Notes

- This service is rendered by `application-openstack-helm.yaml`, which also reads the shared site-level `secret-openstack.yaml` and optional `images-openstack.yaml` files before it reads `ironic/values.yaml`.
