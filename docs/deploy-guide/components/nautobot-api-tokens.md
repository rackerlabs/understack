# nautobot-api-tokens

Integration token bundle for services that call the Nautobot API.

## Deployment Scope

- Cluster scope: global
- Values key: `global.nautobot_api_tokens`
- ArgoCD Application template: `charts/argocd-understack/templates/application-nautobot-api-tokens.yaml`

## How ArgoCD Builds It

- ArgoCD renders only the sources declared directly in the Application template.
- The deploy repo contributes `values.yaml` for this component.
- The deploy repo overlay directory for this component is applied as a second source, so `kustomization.yaml` and any referenced manifests are part of the final Application.

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
global:
  nautobot_api_tokens:
    enabled: true
```

## Deployment Repo Content

Use any secret delivery mechanism you prefer. The contract that matters is the final Kubernetes Secret or manifest shape described below.

Required or commonly required items:

- `kustomization.yaml`: Include one Secret manifest per integration that needs an API token.
- `Per-integration API Secret`: Each integration gets its own explicitly named Secret, and each Secret should expose `username`, `password`, `email`, and `apitoken` so the consuming job or controller can authenticate and identify the token owner.

Optional additions:

- `Additional named token Secrets`: Add more integration-specific Secrets as new workflows or controllers begin calling Nautobot.
