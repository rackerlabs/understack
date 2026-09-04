---
kustomize_paths:
- components/openstack-sync-plugins
deploy_overrides:
  helm:
    mode: none
  kustomize:
    mode: second_source
---

# openstack-sync-plugins

Deploys OpenStack sync custom resources as Kustomize/raw YAML.

It does not ship CRDs, hook code, or operator RBAC. CRDs and hook execution are owned by
`openstack-sync-operator`; this Application applies the CRs that hooks read.

Enable the Application with `site.openstack_sync_plugins.enabled`.

## Deployment Scope

- Cluster scope: site
- Values key: `site.openstack_sync_plugins`
- ArgoCD Application template: `charts/argocd-understack/templates/application-openstack-sync-plugins.yaml`

## How ArgoCD Builds It

{{ component_argocd_builds() }}

## Deployment Repo Content

{{ secrets_disclaimer }}

Shared plugin CRs that should apply to all clusters live in the understack repo
under:

`components/openstack-sync-plugins/`

The shared data entrypoint is:

`components/openstack-sync-plugins/kustomization.yaml`

Site-specific CRs live in the deployment repo under
`<deploy-repo>/<site>/openstack-sync-plugins/` and are listed by that directory's
`kustomization.yaml`.

Hook enablement is separate. Set `plugins.<name>: true` in
`<deploy-repo>/<site>/openstack-sync-operator/values.yaml` only after the site is
pinned to an operator image built with the matching hook under `/hooks/`.

`plugins.<name>: false` does not stop this Application from creating that
plugin's CRs. It only disables the operator hook that processes those CRs. To
stop creating the CRs, disable `site.openstack_sync_plugins.enabled` or remove
the CR files from the relevant `kustomization.yaml`.

Plugin CR files use published editor schemas under `schema/openstack-sync/`.
Those schemas validate the data under `spec`, not the Kubernetes wrapper fields.
Kubernetes validates required fields, types, enums, and defaults through the
operator-owned CRD when ArgoCD applies the CR. The editor schemas are stricter
about unknown spec fields, so add new schema fields with the matching
operator hook/CRD change when a plugin needs new data.

Syncing a plugin CR only converges the OpenStack resource described by that CR.
Any separate operation that uses the synced resource belongs in the plugin's own
examples or operational documentation.
