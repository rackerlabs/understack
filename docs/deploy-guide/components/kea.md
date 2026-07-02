---
charts:
- kea-dhcp
deploy_overrides:
  helm:
    mode: values
  kustomize:
    mode: second_source
---

# kea

Kea DHCP server (ISC Kea) for site network DHCP service.

## Deployment Scope

- Cluster scope: site
- Values key: `site.kea`
- ArgoCD Application template: `charts/argocd-understack/templates/application-kea.yaml`

## How to Enable

Set this component to enabled in your deployment values file:

```yaml title="$CLUSTER_NAME/deploy.yaml"
site:
  kea:
    enabled: true
```

## How ArgoCD Builds It

{{ component_argocd_builds() }}

## Deployment Repo Content

{{ secrets_disclaimer }}

Currently deployed with upstream chart defaults; no required deployment-repo overrides yet.
