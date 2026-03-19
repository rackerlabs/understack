# cert-manager

Certificate management operator installation.

## Deployment Scope

- Cluster scope: global or site
- Values keys: `global.cert_manager`, `site.cert_manager`
- ArgoCD Application template: `charts/argocd-understack/templates/application-cert-manager.yaml`

## How ArgoCD Builds It

- ArgoCD renders Helm chart `cert-manager`.
- The current template does not read a deploy-repo `values.yaml` for this component.
- The current template does not apply a deploy-repo overlay directory for this component.

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
global:
  cert_manager:
    enabled: true
site:
  cert_manager:
    enabled: true
```

## Deployment Repo Content

Use any secret delivery mechanism you prefer. The contract that matters is the final Kubernetes Secret or manifest shape described below.

Required or commonly required items:

- None for this Application today. It installs the upstream chart with inline values and does not consume deploy-repo `values.yaml` or overlay content.

Optional additions:

- Document issuer manifests and challenge-credential Secrets in the `cluster-issuer` component page rather than here.
