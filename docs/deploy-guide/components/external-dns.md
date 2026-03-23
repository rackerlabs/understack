---
charts:
- external-dns chart
deploy_overrides:
  helm:
    mode: values
  kustomize:
    mode: second_source
---

# external-dns

ExternalDNS deployment settings and provider credential wiring.

## Deployment Scope

- Cluster scope: global or site
- Values keys: `global.external_dns`, `site.external_dns`
- ArgoCD Application template: `charts/argocd-understack/templates/application-external-dns.yaml`

## How ArgoCD Builds It

{{ component_argocd_builds() }}

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
global:
  external_dns:
    enabled: true
site:
  external_dns:
    enabled: true
```

## Deployment Repo Content

{{ secrets_disclaimer }}

Required or commonly required items:

- `values.yaml`: Provide the DNS zones, domain filters, ownership settings, and chart values required by your environment.
- `Provider credential Secret`: If your ExternalDNS deployment authenticates through a Secret, create the Secret name referenced by your ExternalDNS values or overlay and populate it with the key names expected by your integration. The current example shape is `username` and `api-key`.

Optional additions:

- `Additional Secret sync resources`: If you use a secret-sync controller, add whatever manifests are needed to materialize that final provider credential Secret without exposing provider details in the docs.
