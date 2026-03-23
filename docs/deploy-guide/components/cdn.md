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

- `values.yaml`: Provide CDN ingress, object-bucket, cache, and runtime settings in `$CLUSTER_NAME/understack-cdn/values.yaml`.

Optional additions:

- `Object storage credential Secret`: If your values reference an authenticated backend instead of anonymous access, create the Secret name referenced by the chart and populate it with the key names that backend expects.
