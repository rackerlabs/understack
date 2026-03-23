---
charts:
- kube-prometheus-stack
deploy_overrides:
  helm:
    mode: values
  kustomize:
    mode: second_source
---

# monitoring

Monitoring stack values plus credential and SSO overlays.

## Deployment Scope

- Cluster scope: global or site
- Values keys: `global.monitoring`, `site.monitoring`
- ArgoCD Application template: `charts/argocd-understack/templates/application-monitoring.yaml`

## How ArgoCD Builds It

{{ component_argocd_builds() }}

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
global:
  monitoring:
    enabled: true
site:
  monitoring:
    enabled: true
```

## Deployment Repo Content

{{ secrets_disclaimer }}

Required or commonly required items:

- `values.yaml`: Provide the chart values for Prometheus, Alertmanager, Grafana, retention, and ingress behavior.
- `Grafana admin credential Secret`: Create the Secret name referenced by your Grafana values and populate it with `username` and `password` for the bootstrap admin account if you manage it outside plain values.
- `Log-backend credential Secret`: Create the Secret name referenced by your logging or metrics values and populate it with `username` and `password` for any authenticated backend that collectors write to.

Optional additions:

- `grafana-sso` Secret: Provide `client-id`, `client-secret`, and `issuer` when Grafana uses OIDC or another delegated login flow.
- `Secret sync bootstrap resources`: Add any generic SecretStore, auth, or CA bundle resources needed to materialize the final Secrets listed above.
