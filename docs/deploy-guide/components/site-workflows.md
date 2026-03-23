---
source_text: ArgoCD renders only the sources declared directly in the Application
  template.
deploy_overrides:
  helm:
    mode: values
  kustomize:
    mode: second_source
---

# site-workflows

Site-level workflow bundle driven by deploy-repo values and overlays.

## Deployment Scope

- Cluster scope: site
- Values key: `site.site_workflows`
- ArgoCD Application template: `charts/argocd-understack/templates/application-site-workflows.yaml`

## How ArgoCD Builds It

{{ component_argocd_builds() }}

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
site:
  site_workflows:
    enabled: true
```

## Deployment Repo Content

{{ secrets_disclaimer }}

Required or commonly required items:

- `values.yaml`: Provide the parameters that the site workflow bundle reads at render time.

Optional additions:

- `Additional workflow manifests`: This overlay directory is wired into ArgoCD, so you can add workflow templates, parameters, RBAC, or Secrets here as site automation grows.
