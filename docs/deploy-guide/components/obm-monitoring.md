---
source_text: ArgoCD renders only the sources declared directly in the Application
  template.
deploy_overrides:
  helm:
    mode: none
  kustomize:
    mode: only_source
---

# obm-monitoring

Out-of-band monitoring WorkflowTemplates, deployed from a deploy-repo Kustomize
overlay into the existing `argo-events` namespace.

## Deployment Scope

- Cluster scope: site
- Values key: `site.obm_monitoring`
- ArgoCD Application template: `charts/argocd-understack/templates/application-obm-monitoring.yaml`

## How ArgoCD Builds It

{{ component_argocd_builds() }}

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
site:
  obm_monitoring:
    enabled: true
```

## Deployment Repo Content

{{ secrets_disclaimer }}

The Application deploys the site overlay at
`$CLUSTER_NAME/obm-monitoring/` from the deployment repository into the
`argo-events` namespace. That namespace, its `workflow` service account, and the
shared executor permissions are owned by the `argo-events` component, so keep
`site.argo_events` and `site.argo_workflows` enabled alongside this one.

Required or commonly required items:

- `kustomization.yaml`: Set `namespace: argo-events` and include the shared
  WorkflowTemplates base plus any site-specific resources.
- API ExternalSecret: Provide the monitoring platform API credentials the
  WorkflowTemplates read at submission time.

Optional additions:

- `Additional overlays or patches`: Pin container images or add site-specific
  parameters, RBAC, or Secrets as the automation grows.

Installing the WorkflowTemplates does not submit a workflow; submission remains
an explicit, operator-driven step.
