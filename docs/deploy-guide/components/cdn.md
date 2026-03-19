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

- ArgoCD renders Helm chart `components/understack-cdn`.
- The deploy repo contributes `understack-cdn/values.yaml` for this component.
- The current template does not apply a deploy-repo overlay directory for this component.

## Deployment Repo Content

Use any secret delivery mechanism you prefer. The contract that matters is the final Kubernetes Secret or manifest shape described below.

Required or commonly required items:

- `values.yaml`: Provide CDN ingress, object-bucket, cache, and runtime settings in `$CLUSTER_NAME/understack-cdn/values.yaml`.

Optional additions:

- `Object storage credential Secret`: If your values reference an authenticated backend instead of anonymous access, create the Secret name referenced by the chart and populate it with the key names that backend expects.
