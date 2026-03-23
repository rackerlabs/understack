---
charts:
- openebs
kustomize_paths:
- operators/openebs
deploy_overrides:
  helm:
    mode: values
  kustomize:
    mode: second_source
---

# openebs

OpenEBS operator values and optional StorageClass overlays.

## Deployment Scope

- Cluster scope: global or site
- Values keys: `global.openebs`, `site.openebs`
- ArgoCD Application template: `charts/argocd-understack/templates/application-openebs.yaml`

## How ArgoCD Builds It

{{ component_argocd_builds() }}

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
global:
  openebs:
    enabled: true
site:
  openebs:
    enabled: true
```

## Deployment Repo Content

{{ secrets_disclaimer }}

Required or commonly required items:

- `values.yaml`: Provide the OpenEBS chart values for your storage topology.

Optional additions:

- `StorageClass manifests`: Add one or more StorageClasses when you need named pools, specific volume parameters, or a different default class. The current example adds an LVM-backed class.
