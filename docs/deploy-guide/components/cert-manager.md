---
charts:
- cert-manager
deploy_overrides:
  helm:
    mode: none
  kustomize:
    mode: none
---

# cert-manager

Certificate management operator installation and site-specific cert-manager configuration.

## Deployment Scope

- Cluster scope: global or site
- Values keys: `global.cert_manager`, `site.cert_manager`
- ArgoCD Application template: `charts/argocd-understack/templates/application-cert-manager.yaml`

## How ArgoCD Builds It

{{ component_argocd_builds() }}

## How to Enable

Enable this component by setting one or both options under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
global:
  cert_manager:
    installApp: true
site:
  cert_manager:
    installApp: true
```

### Options

| Key | Default | Description |
|-----|---------|-------------|
| `installApp` | `false` | Deploy the cert-manager Helm chart |
| `installConfigs` | `false` | Deploy site-specific cert-manager configs from the deploy repo |

To use an externally-managed cert-manager installation while still deploying your site's cert-manager resources:

```yaml title="$CLUSTER_NAME/deploy.yaml"
global:
  cert_manager:
    installApp: false
    installConfigs: true
```

## Deployment Repo Content

{{ secrets_disclaimer }}

When `installConfigs: true`, the Application reads from:

```text
$DEPLOY_REPO/<cluster-name>/cert-manager/
```

Required or commonly required items:

- None required. With `installApp: true` the chart is installed with inline values and does not consume deploy-repo content.

Optional additions:

- For `ClusterIssuer` and `Issuer` resources, prefer the dedicated [`cluster-issuer`](cluster-issuer.md) component.
- Other cert-manager configuration resources can be placed in the `cert-manager/` deploy-repo path when `installConfigs: true`.
