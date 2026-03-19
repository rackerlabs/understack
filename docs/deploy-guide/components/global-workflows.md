# global-workflows

Global automation workflows.

## Deployment Scope

- Cluster scope: global
- Values key: `global.global_workflows`
- ArgoCD Application template: `charts/argocd-understack/templates/application-global-workflows.yaml`

## How to Enable

Set this component to enabled in your deployment values file:

```yaml title="$CLUSTER_NAME/deploy.yaml"
global:
  global_workflows:
    enabled: true
```

## How ArgoCD Builds It

- ArgoCD renders only the sources declared directly in the Application template.
- The current template does not read a deploy-repo `values.yaml` for this component.
- The deploy repo overlay directory for this component is applied as a second source, so `kustomization.yaml` and any referenced manifests are part of the final Application.

## Deployment Repo Content

Use any secret delivery mechanism you prefer. The contract that matters is the final Kubernetes Secret or manifest shape described below.

Required or commonly required items:

- `kustomization.yaml`: Because this Application points directly at the deploy overlay, the overlay must include the base global workflow manifests or a remote/base reference that brings them in.

Optional additions:

- `Workflow manifests`: Add workflow templates, RBAC, parameters, or Secrets needed by global automation.
