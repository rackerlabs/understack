---
kustomize_paths:
- components/ovn/
deploy_overrides:
  helm:
    mode: values
  kustomize:
    mode: second_source
---

# ovn

OVN configuration values for a site deployment.

## Deployment Scope

- Cluster scope: site
- Values key: `site.ovn`
- ArgoCD Application template: `charts/argocd-understack/templates/application-ovn.yaml`

## How ArgoCD Builds It

{{ component_argocd_builds() }}

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
site:
  ovn:
    enabled: true
```

## Deployment Repo Content

{{ secrets_disclaimer }}

Required or commonly required items:

- `values.yaml`: Provide the OVN-specific values consumed by the shared base manifests.

Optional additions:

- No extra manifests are present in the current example overlay, but this directory is available if you later need OVN-specific Kustomize resources.
