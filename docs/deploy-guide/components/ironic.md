---
charts:
- ironic
kustomize_paths:
- components/ironic/
argocd_extra:
- The shared site-level `secret-openstack.yaml` and optional `images-openstack.yaml`
  files are loaded before the service-specific values file.
deploy_overrides:
  helm:
    mode: values
  kustomize:
    mode: second_source
---

# ironic

Ironic control-plane overlays for provisioning services and site networking.

## Deployment Scope

- Cluster scope: site
- Values key: `site.ironic`
- ArgoCD Application template: `charts/argocd-understack/templates/application-openstack-helm.yaml`

## How ArgoCD Builds It

{{ component_argocd_builds() }}

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
site:
  ironic:
    enabled: true
```

## Deployment Repo Content

{{ secrets_disclaimer }}

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
