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

## Notes

- The current ArgoCD template installs the upstream chart directly and does not consume a deploy-repo values file or overlay directory for this component.
- Document issuer-specific Secrets and issuer manifests in the `cluster-issuer` page instead of here.
