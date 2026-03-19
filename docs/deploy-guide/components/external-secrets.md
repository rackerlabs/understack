# external-secrets

External Secrets operator installation.

## Deployment Scope

- Cluster scope: global or site
- Values keys: `global.external_secrets`, `site.external_secrets`
- ArgoCD Application template: `charts/argocd-understack/templates/application-external-secrets.yaml`

## How ArgoCD Builds It

- ArgoCD renders Kustomize path `operators/external-secrets`.
- The current template does not read a deploy-repo `values.yaml` for this component.
- The current template does not apply a deploy-repo overlay directory for this component.

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
global:
  external_secrets:
    enabled: true
site:
  external_secrets:
    enabled: true
```

## Deployment Repo Content

Use any secret delivery mechanism you prefer. The contract that matters is the final Kubernetes Secret or manifest shape described below.

Required or commonly required items:

- None for this Application today. It deploys the shared operator manifests directly and does not read deploy-repo values or overlay manifests for this component.

Optional additions:

- Document provider-specific SecretStores and authentication material only where a consuming component needs the resulting Secret shape.
