# cluster-issuer

Deployment-provided cert-manager ClusterIssuer resources.

## Deployment Scope

- Cluster scope: global, site
- Values key: `global.cluster_issuer / site.cluster_issuer`
- ArgoCD Application template: `charts/argocd-understack/templates/application-cluster-issuer.yaml`

## How to Enable

Set this component to enabled in your deployment values file:

```yaml title="$CLUSTER_NAME/deploy.yaml"
global:
  cluster_issuer:
    enabled: true
```

## Deployment Repo Overrides

Use your deployment repo to provide environment-specific values and overlays.
Start with [Configuring Components](../components/index.md) and [Deploy Repo](../deploy-repo.md).

## Notes

- Document prerequisites for this component.
- Document required secrets and config inputs.
- Document validation checks and troubleshooting commands.
