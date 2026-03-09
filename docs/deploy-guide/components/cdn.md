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

## Deployment Repo Overrides

Use your deployment repo to provide environment-specific values and overlays.
Start with [Configuring Components](../components/index.md) and [Deploy Repo](../deploy-repo.md).

## Notes

- Document prerequisites for this component.
- Document required secrets and config inputs.
- Document validation checks and troubleshooting commands.
