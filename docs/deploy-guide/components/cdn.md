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

- Enable `supportassist.enabled` to create a separate private `supportassist`
  bucket and signing sidecar. Rook generates its credentials Secret and
  endpoint ConfigMap; do not create a public bucket policy.
- Add a site HTTPRoute on the internal gateway for PUT `/supportassist/` to
  `understack-cdn/cdn-edge` port `8081`. The firmware listener uses port `80`.
  An IP-based URL works for iDRACs without DNS configured.

SupportAssist uploads are limited to one active request per CDN pod and a
1 GiB body. Concurrent uploads return 503; oversized uploads return 413.
The signer buffers uploads and has a 6 GiB memory limit. See the
[CDN README](https://github.com/rackerlabs/understack/blob/main/components/understack-cdn/README.md#supportassist-uploads)
for resource requirements and access behavior.
