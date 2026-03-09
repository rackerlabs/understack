# cilium

Cilium CNI and networking policies.

## Deployment Scope

- Cluster scope: global, site
- Values key: `global.cilium / site.cilium`
- ArgoCD Application template: `charts/argocd-understack/templates/application-cilium.yaml`

## How to Enable

Set this component to enabled in your deployment values file:

```yaml title="$CLUSTER_NAME/deploy.yaml"
global:
  cilium:
    enabled: true
```

## Deployment Repo Overrides

Use your deployment repo to provide environment-specific values and overlays.
Start with [Configuring Components](../components/index.md) and [Deploy Repo](../deploy-repo.md).

## Notes

- Document prerequisites for this component.
- Document required secrets and config inputs.
- Document validation checks and troubleshooting commands.
