---
kustomize_paths:
- workflows/argo-events
deploy_overrides:
  helm:
    mode: none
  kustomize:
    mode: second_source
---

# argo-events-workflows

Workflow templates that integrate Argo Events with the broader platform.

## Deployment Scope

- Cluster scope: site
- Values key: `site.argo_events_workflows`
- ArgoCD Application template: `charts/argocd-understack/templates/application-argo-events-workflows.yaml`

## How ArgoCD Builds It

{{ component_argocd_builds() }}

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
site:
  argo_events_workflows:
    enabled: true
```

## Deployment Repo Content

{{ secrets_disclaimer }}

Required or commonly required items:

- `nautobot-token` Secret: Provide `username`, `token`, and `hostname` so the workflow templates can authenticate to the source-of-truth API.
- `kustomization.yaml`: Include the Secrets and any additional workflow templates or parameter files that should be packaged with this overlay.

Optional additions:

- `Additional integration Secrets`: Add more Secrets beside the API token if individual workflows need their own credentials or endpoints.
