---
charts:
- components/understack-cdn
deploy_overrides:
  helm:
    mode: values_files
    paths:
    - understack-cdn/values.yaml
  kustomize:
    mode: none
---

# cdn

UnderStack CDN service deployment.

## Deployment Scope

- Cluster scope: site
- Values key: `site.understack_cdn`
- ArgoCD Application template: `charts/argocd-understack/templates/application-cdn.yaml`

## How to Enable

Set this component to enabled in your deployment values file:

```yaml title="$CLUSTER_NAME/deploy.yaml"
site:
  understack_cdn:
    enabled: true
```

## How ArgoCD Builds It

{{ component_argocd_builds() }}

## Deployment Repo Content

{{ secrets_disclaimer }}

Required or commonly required items:

- `values.yaml`: Provide CDN object-bucket and cache settings in `$CLUSTER_NAME/understack-cdn/values.yaml`.

Optional additions:

- Enable `supportassist.enabled` to create a dedicated `supportassist` PVC
  for HTTP PUT uploads. Set `supportassist.storageSize` (default `40Gi`) and
  `supportassist.storageClassName` (default `openebs-lvm`) for the site.
  The site must also provide a Secret named `supportassist-download-auth` with
  an `htpasswd` key for authenticated archive reads; the pod waits for it.
  With SupportAssist enabled, `cdn-edge` upgrades use `Recreate`, so the CDN
  is briefly unavailable while the pod restarts.
- Add a site HTTPRoute on the internal gateway for PUT `/supportassist/` to
  `understack-cdn/cdn-edge` port `8081`. The firmware listener uses port `80`.
  An IP-based URL works for iDRACs without DNS configured.

NGINX WebDAV stores uploaded archives on the PVC. Retrieve completed archives
with `kubectl cp` and monitor available disk space. Operators manage archive
retention and capacity; uploads fail when the volume fills.
See the [CDN README](https://github.com/rackerlabs/understack/blob/main/components/understack-cdn/README.md#supportassist-uploads)
for retrieval commands, timeouts and access behavior.
