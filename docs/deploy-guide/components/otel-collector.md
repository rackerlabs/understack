---
source_text: ArgoCD renders only the sources declared directly in the Application
  template.
deploy_overrides:
  helm:
    mode: none
  kustomize:
    mode: only_source
---

# otel-collector

OpenTelemetry collector resources supplied directly from the deploy repo.

## Deployment Scope

- Cluster scope: global or site
- Values keys: `global.otel_collector`, `site.otel_collector`
- ArgoCD Application template: `charts/argocd-understack/templates/application-otel-collector.yaml`

## How ArgoCD Builds It

{{ component_argocd_builds() }}

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
global:
  otel_collector:
    enabled: true
site:
  otel_collector:
    enabled: true
```

## Deployment Repo Content

{{ secrets_disclaimer }}

Required or commonly required items:

- `kustomization.yaml`: Include the collector manifests that should run in this environment.
- `Backend credential Secret`: Create the Secret name referenced by your collector manifests and populate it with `username` and `password` when exporters write to an authenticated log or metrics backend.

Optional additions:

- `Node collector manifests`: Add a DaemonSet, RBAC, or other collector workloads if you want node-level telemetry. The current example includes both.
- `Additional collector pipelines`: Add more Deployments, ConfigMaps, or Secrets as telemetry requirements grow.
