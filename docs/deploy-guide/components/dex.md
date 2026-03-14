# dex

Dex identity provider configuration and client registrations.

## Deployment Scope

- Cluster scope: global
- Values key: `global.dex`
- ArgoCD Application template: `charts/argocd-understack/templates/application-dex.yaml`

## How ArgoCD Builds It

- ArgoCD renders Helm chart `dex`, Kustomize path `components/dex`.
- The deploy repo contributes `values.yaml` for this component.
- The deploy repo overlay directory for this component is applied as a second source, so `kustomization.yaml` and any referenced manifests are part of the final Application.

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
global:
  dex:
    enabled: true
```

## Deployment Repo Content

Use any secret delivery mechanism you prefer. The contract that matters is the final Kubernetes Secret or manifest shape described below.

Required or commonly required items:

- `values.yaml`: Provide the Dex runtime settings that are specific to your identity environment.
- `connector-sso` Secret: Provide the client credentials for the upstream identity connector. The example shape is `client-id`, `client-secret`, and `issuer`.
- `client-*-sso` Secrets: Create one Secret per relying party that should authenticate through Dex. The common key shape is `client-id`, `client-secret`, and `issuer`.

Optional additions:

- `client-localdev-sso` or other local/test client Secrets: Add extra client registrations for development or troubleshooting environments without changing the shared base manifests.
