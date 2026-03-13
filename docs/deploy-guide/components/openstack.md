# openstack

Base site-level OpenStack shared resources and bootstrap content.

## Deployment Scope

- Cluster scope: site
- Values key: `site.openstack`
- ArgoCD Application template: `charts/argocd-understack/templates/application-openstack.yaml`

## How ArgoCD Builds It

- ArgoCD renders Kustomize path `components/openstack`.
- The deploy repo contributes `values.yaml` for this component.
- The deploy repo overlay directory for this component is applied as a second source, so `kustomization.yaml` and any referenced manifests are part of the final Application.

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
site:
  openstack:
    enabled: true
```

## Deployment Repo Content

Use any secret delivery mechanism you prefer. The contract that matters is the final Kubernetes Secret or manifest shape described below.

Required or commonly required items:

- `values.yaml`: Provide the OpenStack-wide values used by the shared base component.
- `nautobot-token` Secret: Provide `username`, `token`, and `hostname` for any jobs or controllers that need to query the source-of-truth service.

Optional additions:

- `Hardware and inventory bundles`: Add device types, flavor catalogs, location types, locations, rack groups, and racks when the site should be bootstrapped with platform inventory data.
- `Service-user secret sync bundle`: Add manifests that materialize the service-user Secrets consumed by automation or Keystone integrations.
- `Secret sync bootstrap resources`: Add the generic auth or SecretStore resources required by your chosen secret workflow, but document only the final Secret shapes consumed by OpenStack.
