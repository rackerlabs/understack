# argo-events-workflows

Workflow templates that integrate Argo Events with the broader platform.

## Deployment Scope

- Cluster scope: site
- Values key: `site.argo_events_workflows`
- ArgoCD Application template: `charts/argocd-understack/templates/application-argo-events-workflows.yaml`

## How ArgoCD Builds It

- ArgoCD renders Kustomize path `workflows/argo-events`.
- The current template does not read a deploy-repo `values.yaml` for this component.
- The deploy repo overlay directory for this component is applied as a second source, so `kustomization.yaml` and any referenced manifests are part of the final Application.

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
site:
  argo_events_workflows:
    enabled: true
```

## Deployment Repo Content

Use any secret delivery mechanism you prefer. The contract that matters is the final Kubernetes Secret or manifest shape described below.

Required or commonly required items:

- `nautobot-token` Secret: Provide `username`, `token`, and `hostname` so the workflow templates can authenticate to the source-of-truth API.
- `kustomization.yaml`: Include the Secrets and any additional workflow templates or parameter files that should be packaged with this overlay.

Optional additions:

- `Additional integration Secrets`: Add more Secrets beside the API token if individual workflows need their own credentials or endpoints.
