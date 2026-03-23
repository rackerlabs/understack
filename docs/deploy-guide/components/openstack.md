---
kustomize_paths:
- components/openstack
deploy_overrides:
  helm:
    mode: values
  kustomize:
    mode: second_source
---

# openstack

Base site-level OpenStack shared resources and bootstrap content.

## Deployment Scope

- Cluster scope: site
- Values key: `site.openstack`
- ArgoCD Application template: `charts/argocd-understack/templates/application-openstack.yaml`

## How ArgoCD Builds It

{{ component_argocd_builds() }}

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
site:
  openstack:
    enabled: true
```

## Deployment Repo Content

{{ secrets_disclaimer }}

Required or commonly required items:

- `values.yaml`: Provide the OpenStack-wide values used by the shared base component.
- `nautobot-token` Secret: Provide `username`, `token`, and `hostname` for any jobs or controllers that need to query the source-of-truth service.

Optional additions:

- `Hardware and inventory bundles`: Add device types, flavor catalogs, location types, locations, rack groups, and racks when the site should be bootstrapped with platform inventory data.
- `Service-user secret sync bundle`: Add manifests that materialize the service-user Secrets consumed by automation or Keystone integrations.
- `Secret sync bootstrap resources`: Add the generic auth or SecretStore resources required by your chosen secret workflow, but document only the final Secret shapes consumed by OpenStack.
