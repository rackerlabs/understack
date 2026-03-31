---
kustomize_paths:
- operators/external-secrets
deploy_overrides:
  helm:
    mode: none
  kustomize:
    mode: none
---

# external-secrets

External Secrets operator installation and site-specific ESO configuration.

## Deployment Scope

- Cluster scope: global or site
- Values keys: `global.external_secrets`, `site.external_secrets`
- ArgoCD Application template: `charts/argocd-understack/templates/application-external-secrets.yaml`

## How ArgoCD Builds It

{{ component_argocd_builds() }}

## How to Enable

Enable this component by setting one or both options under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
global:
  external_secrets:
    installApp: true
site:
  external_secrets:
    installApp: true
```

### Options

| Key | Default | Description |
|-----|---------|-------------|
| `installApp` | `false` | Deploy the External Secrets Operator from the understack repo |
| `installConfigs` | `false` | Deploy site-specific ESO configs from the deploy repo |

To use an externally-managed ESO installation (e.g. the operator is already installed by another team) while still deploying your site's ESO resources:

```yaml title="$CLUSTER_NAME/deploy.yaml"
global:
  external_secrets:
    installApp: false
    installConfigs: true
```

## Deployment Repo Content

{{ secrets_disclaimer }}

When `installConfigs: true`, the Application reads from:

```text
$DEPLOY_REPO/<cluster-name>/external-secrets/
```

Place any site-specific ESO resources here, for example:

- `ClusterSecretStore` manifests connecting to your secrets backend
- `ExternalSecret` objects for secrets that don't belong to a specific component

Required or commonly required items:

- None required. With `installApp: true` the operator manifests are deployed directly from the understack repo with no deploy-repo content needed.

Optional additions:

- Provider-specific `ClusterSecretStore` and authentication `Secret` objects in the `external-secrets/` deploy-repo path when `installConfigs: true`.
