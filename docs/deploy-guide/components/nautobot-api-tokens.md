---
source_text: ArgoCD renders only the sources declared directly in the Application
  template.
deploy_overrides:
  helm:
    mode: values
  kustomize:
    mode: second_source
---

# nautobot-api-tokens

Integration token bundle for services that call the Nautobot API.

## Deployment Scope

- Cluster scope: global
- Values key: `global.nautobot_api_tokens`
- ArgoCD Application template: `charts/argocd-understack/templates/application-nautobot-api-tokens.yaml`

## How ArgoCD Builds It

{{ component_argocd_builds() }}

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
global:
  nautobot_api_tokens:
    enabled: true
```

## Deployment Repo Content

{{ secrets_disclaimer }}

Required or commonly required items:

- `kustomization.yaml`: Include one Secret manifest per integration that needs an API token.
- `Per-integration API Secret`: Each integration gets its own explicitly named Secret, and each Secret should expose `username`, `password`, `email`, and `apitoken` so the consuming job or controller can authenticate and identify the token owner.

Optional additions:

- `Additional named token Secrets`: Add more integration-specific Secrets as new workflows or controllers begin calling Nautobot.
