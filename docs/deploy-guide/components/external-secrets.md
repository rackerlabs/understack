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

## Notes

- The current ArgoCD template deploys the shared operator manifests directly and does not read deploy-repo values or overlay manifests for this component.
- Provider-specific SecretStores and authentication material should be documented only where a consuming component needs the resulting Secret shape.
