---
source_text: ArgoCD renders only the sources declared directly in the Application
  template.
deploy_overrides:
  helm:
    mode: none
  kustomize:
    mode: second_source
---

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

{{ component_argocd_builds() }}

## Deployment Repo Content

{{ secrets_disclaimer }}

Required or commonly required items:

- `kustomization.yaml`: Because this Application points directly at the deploy overlay, the overlay must include the base global workflow manifests or a remote/base reference that brings them in.

Optional additions:

- `Workflow manifests`: Add workflow templates, RBAC, parameters, or Secrets needed by global automation.
