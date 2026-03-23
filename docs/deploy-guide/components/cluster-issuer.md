---
source_text: ArgoCD renders only the sources declared directly in the Application
  template.
deploy_overrides:
  helm:
    mode: none
  kustomize:
    mode: only_source
---

# cluster-issuer

Cluster-scoped certificate issuer configuration.

## Deployment Scope

- Cluster scope: global or site
- Values keys: `global.cluster_issuer`, `site.cluster_issuer`
- ArgoCD Application template: `charts/argocd-understack/templates/application-cluster-issuer.yaml`

## How ArgoCD Builds It

{{ component_argocd_builds() }}

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
global:
  cluster_issuer:
    enabled: true
site:
  cluster_issuer:
    enabled: true
```

## Deployment Repo Content

{{ secrets_disclaimer }}

Required or commonly required items:

- `ClusterIssuer manifest`: Define the issuer, solver, and policy that cert-manager should use for cluster certificates.
- `DNS or API credential Secret`: When the issuer solves challenges through an external API, create the Secret name referenced by your `ClusterIssuer` manifest and populate it with `username` and `api-key` keys, or the equivalent keys your issuer expects.

Optional additions:

- `Additional issuer manifests`: Add more issuers if you need separate trust domains, challenge solvers, or certificate policies.
