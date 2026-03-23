---
charts:
- karma
deploy_overrides:
  helm:
    mode: values
  kustomize:
    mode: second_source
---

# karma

Karma alert dashboard for Alertmanager.

## Deployment Scope

- Cluster scope: global, site
- Values key: `global.karma / site.karma`
- ArgoCD Application template: `charts/argocd-understack/templates/application-karma.yaml`

## How to Enable

Set this component to enabled in your deployment values file:

```yaml title="$CLUSTER_NAME/deploy.yaml"
global:
  karma:
    enabled: true
```

## How ArgoCD Builds It

{{ component_argocd_builds() }}

## Deployment Repo Content

{{ secrets_disclaimer }}

Required or commonly required items:

- `values.yaml`: Provide Alertmanager endpoints, ingress, auth, and UI settings.
- `kustomization.yaml`: Include any Secret or manifest resources referenced by your Karma values.

Optional additions:

- `SSO or proxy credential Secret`: Create the Secret name referenced by your values or overlay and populate it with the keys expected by your authentication flow.
