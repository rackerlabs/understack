# argo-workflows

Argo Workflows installation content sourced from the deploy repo.

## Deployment Scope

- Cluster scope: global or site
- Values keys: `global.argo_workflows`, `site.argo_workflows`
- ArgoCD Application template: `charts/argocd-understack/templates/application-argo-workflows.yaml`

## How ArgoCD Builds It

- ArgoCD renders only the sources declared directly in the Application template.
- The current template does not read a deploy-repo `values.yaml` for this component.
- The deploy repo overlay directory for this component is applied as a second source, so `kustomization.yaml` and any referenced manifests are part of the final Application.

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
global:
  argo_workflows:
    enabled: true
site:
  argo_workflows:
    enabled: true
```

## Deployment Repo Content

Use any secret delivery mechanism you prefer. The contract that matters is the final Kubernetes Secret or manifest shape described below.

Required or commonly required items:

- `kustomization.yaml`: Because this Application points directly at the deploy overlay, the overlay must include the base workflow manifests or a remote/base reference that brings them in.
- `argo-sso` Secret: If web SSO is enabled, provide `client-id`, `client-secret`, and `issuer` for the workflow UI.

Optional additions:

- `Extra workflow manifests`: Add workflow templates, RBAC, notifications, or UI settings directly in this overlay.
