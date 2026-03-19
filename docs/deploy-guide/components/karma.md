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

- ArgoCD renders Helm chart `karma`.
- The deploy repo contributes `values.yaml` for this component.
- The deploy repo overlay directory for this component is applied as a second source, so `kustomization.yaml` and any referenced manifests are part of the final Application.

## Deployment Repo Content

Use any secret delivery mechanism you prefer. The contract that matters is the final Kubernetes Secret or manifest shape described below.

Required or commonly required items:

- `values.yaml`: Provide Alertmanager endpoints, ingress, auth, and UI settings.
- `kustomization.yaml`: Include any Secret or manifest resources referenced by your Karma values.

Optional additions:

- `SSO or proxy credential Secret`: Create the Secret name referenced by your values or overlay and populate it with the keys expected by your authentication flow.
