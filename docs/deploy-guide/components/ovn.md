# ovn

OVN configuration values for a site deployment.

## Deployment Scope

- Cluster scope: site
- Values key: `site.ovn`
- ArgoCD Application template: `charts/argocd-understack/templates/application-ovn.yaml`

## How ArgoCD Builds It

- ArgoCD renders Kustomize path `components/ovn/`.
- The deploy repo contributes `values.yaml` for this component.
- The deploy repo overlay directory for this component is applied as a second source, so `kustomization.yaml` and any referenced manifests are part of the final Application.

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
site:
  ovn:
    enabled: true
```

## Deployment Repo Content

Use any secret delivery mechanism you prefer. The contract that matters is the final Kubernetes Secret or manifest shape described below.

Required or commonly required items:

- `values.yaml`: Provide the OVN-specific values consumed by the shared base manifests.

Optional additions:

- No extra manifests are present in the current example overlay, but this directory is available if you later need OVN-specific Kustomize resources.
