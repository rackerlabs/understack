# site-workflows

Site-level workflow bundle driven by deploy-repo values and overlays.

## Deployment Scope

- Cluster scope: site
- Values key: `site.site_workflows`
- ArgoCD Application template: `charts/argocd-understack/templates/application-site-workflows.yaml`

## How ArgoCD Builds It

- ArgoCD renders only the sources declared directly in the Application template.
- The deploy repo contributes `values.yaml` for this component.
- The deploy repo overlay directory for this component is applied as a second source, so `kustomization.yaml` and any referenced manifests are part of the final Application.

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
site:
  site_workflows:
    enabled: true
```

## Deployment Repo Content

Use any secret delivery mechanism you prefer. The contract that matters is the final Kubernetes Secret or manifest shape described below.

Required or commonly required items:

- `values.yaml`: Provide the parameters that the site workflow bundle reads at render time.

Optional additions:

- `Additional workflow manifests`: This overlay directory is wired into ArgoCD, so you can add workflow templates, parameters, RBAC, or Secrets here as site automation grows.
