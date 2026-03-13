# monitoring

Monitoring stack values plus credential and SSO overlays.

## Deployment Scope

- Cluster scope: global or site
- Values keys: `global.monitoring`, `site.monitoring`
- ArgoCD Application template: `charts/argocd-understack/templates/application-monitoring.yaml`

## How ArgoCD Builds It

- ArgoCD renders Helm chart `kube-prometheus-stack`.
- The deploy repo contributes `values.yaml` for this component.
- The deploy repo overlay directory for this component is applied as a second source, so `kustomization.yaml` and any referenced manifests are part of the final Application.

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

Use any secret delivery mechanism you prefer. The contract that matters is the final Kubernetes Secret or manifest shape described below.

Required or commonly required items:

- `values.yaml`: Provide the chart values for Prometheus, Alertmanager, Grafana, retention, and ingress behavior.
- `Grafana admin credential Secret`: Create the Secret name referenced by your Grafana values and populate it with `username` and `password` for the bootstrap admin account if you manage it outside plain values.
- `Log-backend credential Secret`: Create the Secret name referenced by your logging or metrics values and populate it with `username` and `password` for any authenticated backend that collectors write to.

Optional additions:

- `grafana-sso` Secret: Provide `client-id`, `client-secret`, and `issuer` when Grafana uses OIDC or another delegated login flow.
- `Secret sync bootstrap resources`: Add any generic SecretStore, auth, or CA bundle resources needed to materialize the final Secrets listed above.
