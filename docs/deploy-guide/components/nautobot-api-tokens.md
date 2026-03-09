# nautobot-api-tokens

Nautobot API token generation jobs.

## Deployment Scope

- Cluster scope: global
- Values key: `global.nautobot_api_tokens`
- ArgoCD Application template: `charts/argocd-understack/templates/application-nautobot-api-tokens.yaml`

## How to Enable

Set this component to enabled in your deployment values file:

```yaml title="$CLUSTER_NAME/deploy.yaml"
global:
  nautobot_api_tokens:
    enabled: true
```

## Deployment Repo Overrides

Use your deployment repo to provide environment-specific values and overlays.
Start with [Configuring Components](../components/index.md) and [Deploy Repo](../deploy-repo.md).

## Notes

- Document prerequisites for this component.
- Document required secrets and config inputs.
- Document validation checks and troubleshooting commands.
