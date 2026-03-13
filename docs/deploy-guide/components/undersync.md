# undersync

Undersync application overlays and deployment-specific Secrets.

## Deployment Scope

- Cluster scope: site
- Values key: `site.undersync`
- ArgoCD Application template: `charts/argocd-understack/templates/application-undersync.yaml`

## How ArgoCD Builds It

- ArgoCD renders Kustomize path `components/undersync`.
- The current template does not read a deploy-repo `values.yaml` for this component.
- The deploy repo overlay directory for this component is applied as a second source, so `kustomization.yaml` and any referenced manifests are part of the final Application.

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
site:
  undersync:
    enabled: true
```

## Deployment Repo Content

Use any secret delivery mechanism you prefer. The contract that matters is the final Kubernetes Secret or manifest shape described below.

Required or commonly required items:

- `kustomization.yaml`: Include the override manifests and Secrets that must be applied with the shared base component.
- `settings-file` Secret: Provide a `settings-file.yaml` key containing the rendered application settings file.
- `dockerconfigjson-github-com` Secret: Provide `.dockerconfigjson` when the deployment pulls from a private registry.

Optional additions:

- `Deployment override manifest`: Add a Deployment or patch if this environment needs image, volume, or runtime changes beyond the shared base. The current example includes a full Deployment override.
