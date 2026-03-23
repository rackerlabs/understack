---
source_text: ArgoCD renders the matching OpenStack Helm chart for each enabled site
  service and the companion Kustomize path `components/<service>/`.
argocd_extra:
- The shared site-level `secret-openstack.yaml` and optional `images-openstack.yaml`
  files are loaded before the service-specific values file.
- The deploy repo contributes `secret-openstack.yaml`, optional `images-openstack.yaml`,
  and `<service>/values.yaml`.
- The deploy repo overlay directory for each enabled service is applied as a second
  source, so `<service>/kustomization.yaml` and any referenced manifests are part
  of the final Application.
---

# openstack-helm

Shared deployment contract for the per-service OpenStack Helm Applications.

## Deployment Scope

- Cluster scope: site
- Values key: `site.<service>.enabled`
- ArgoCD Application template: `charts/argocd-understack/templates/application-openstack-helm.yaml`

## How ArgoCD Builds It

{{ component_argocd_builds() }}

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
site:
  <service>:
    enabled: true
```

## Deployment Repo Content

{{ secrets_disclaimer }}

Required or commonly required items:

- `secret-openstack.yaml`: Provide the shared endpoint hostnames, scheme and port overrides, and cluster-wide secret material used by multiple OpenStack services. Typical content includes memcache keys plus per-service database and messaging passwords.
- `<service>/values.yaml`: Provide service-specific values in each enabled service directory such as `glance/values.yaml`, `nova/values.yaml`, or `neutron/values.yaml`.
- `<service>/kustomization.yaml`: Use the per-service overlay to add any service-specific Secrets, ConfigMaps, Services, or patches.

Optional additions:

- `images-openstack.yaml`: Pin or override the container images used across the OpenStack Helm services when you do not want the defaults.
- `Per-service Secrets`: Add only the service credentials or config files that are not already expressed in `secret-openstack.yaml`.
- `Per-service overlay resources`: Add patches, Service manifests, or ConfigMaps to the individual service directories as needed.
