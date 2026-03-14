# openebs

OpenEBS operator values and optional StorageClass overlays.

## Deployment Scope

- Cluster scope: global or site
- Values keys: `global.openebs`, `site.openebs`
- ArgoCD Application template: `charts/argocd-understack/templates/application-openebs.yaml`

## How ArgoCD Builds It

- ArgoCD renders Helm chart `openebs`, Kustomize path `operators/openebs`.
- The deploy repo contributes `values.yaml` for this component.
- The deploy repo overlay directory for this component is applied as a second source, so `kustomization.yaml` and any referenced manifests are part of the final Application.

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

Use any secret delivery mechanism you prefer. The contract that matters is the final Kubernetes Secret or manifest shape described below.

Required or commonly required items:

- `values.yaml`: Provide the OpenEBS chart values for your storage topology.

Optional additions:

- `StorageClass manifests`: Add one or more StorageClasses when you need named pools, specific volume parameters, or a different default class. The current example adds an LVM-backed class.
