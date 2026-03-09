# external-secrets

External Secrets Operator and secret synchronization.

## Deployment Scope

- Cluster scope: global, site
- Values key: `global.external_secrets / site.external_secrets`
- ArgoCD Application template: `charts/argocd-understack/templates/application-external-secrets.yaml`

## How to Enable

Set this component to enabled in your deployment values file:

```yaml title="$CLUSTER_NAME/deploy.yaml"
global:
  external_secrets:
    enabled: true
```

## Deployment Repo Overrides

Use your deployment repo to provide environment-specific values and overlays.
Start with [Configuring Components](../components/index.md) and [Deploy Repo](../deploy-repo.md).

## Notes

- Document prerequisites for this component.
- Document required secrets and config inputs.
- Document validation checks and troubleshooting commands.
