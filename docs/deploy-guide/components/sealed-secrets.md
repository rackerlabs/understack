# sealed-secrets

Sealed Secrets controller installation.

## Deployment Scope

- Cluster scope: global or site
- Values keys: `global.sealed_secrets`, `site.sealed_secrets`
- ArgoCD Application template: `charts/argocd-understack/templates/application-sealed-secrets.yaml`

## How ArgoCD Builds It

- ArgoCD renders Kustomize path `bootstrap/sealed-secrets`.
- The current template does not read a deploy-repo `values.yaml` for this component.
- The current template does not apply a deploy-repo overlay directory for this component.

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
global:
  sealed_secrets:
    enabled: true
site:
  sealed_secrets:
    enabled: true
```

## Notes

- The current ArgoCD template deploys the shared bootstrap manifests directly and does not consume deploy-repo values or overlay manifests for this component.
- Document individual decrypted Secret shapes on the component pages that consume them rather than here.
