---
kustomize_paths:
- components/undersync
deploy_overrides:
  helm:
    mode: none
  kustomize:
    mode: second_source
---

# undersync

Undersync application overlays and deployment-specific Secrets.

## Deployment Scope

- Cluster scope: site
- Values key: `site.undersync`
- ArgoCD Application template: `charts/argocd-understack/templates/application-undersync.yaml`

## How ArgoCD Builds It

{{ component_argocd_builds() }}

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
site:
  undersync:
    enabled: true
```

## Deployment Repo Content

{{ secrets_disclaimer }}

Required or commonly required items:

- `kustomization.yaml`: Include the override manifests and Secrets that must be applied with the shared base component.
- `settings-file` Secret: Provide a `settings-file.yaml` key containing the rendered application settings file.
- `dockerconfigjson-github-com` Secret: Provide `.dockerconfigjson` when the deployment pulls from a private registry.

Optional additions:

- `Deployment override manifest`: Add a Deployment or patch if this environment needs image, volume, or runtime changes beyond the shared base. The current example includes a full Deployment override.
