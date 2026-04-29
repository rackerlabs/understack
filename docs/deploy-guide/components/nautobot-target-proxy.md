---
charts:
- nautobot-target-proxy
deploy_overrides:
  helm:
    mode: values
  kustomize:
    mode: second_source
---

# nautobot-target-proxy

FastAPI proxy service that fronts Nautobot target lookups for site deployments.

## Deployment Scope

- Cluster scope: site
- Values key: `site.nautobot_target_proxy`
- ArgoCD Application template: `charts/argocd-understack/templates/application-nautobot-target-proxy.yaml`

## How ArgoCD Builds It

{{ component_argocd_builds() }}

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
site:
  nautobot_target_proxy:
    enabled: true
```

## Deployment Repo Content

{{ secrets_disclaimer }}

Required or commonly required items:

- `values.yaml`: Provide deployment-specific overrides such as the Nautobot base URL, image settings, and any scheduling or resource changes for this environment.
- `nautobot-token` Secret: Provide the key referenced by `nautobot.tokenSecretRef` so the proxy can authenticate to the Nautobot API.
- `cluster-data` ConfigMap: Provide the key referenced by `nautobot.clusterDataConfigMapRef` so the proxy receives `UNDERSTACK_PARTITION`.

Optional additions:

- `dockerconfigjson-github-com` Secret: Provide `.dockerconfigjson` if this deployment pulls the proxy image from a private registry and reference it through `imagePullSecrets`.
- `Deployment override manifest`: Add patches or extra manifests in the component overlay directory if this site needs pod-level changes that are clearer to manage as Kubernetes resources instead of Helm values alone.

## Notes

- The chart deploys the proxy in the `nautobot` namespace and exposes it with a ClusterIP Service on port `8000` by default.
- The ArgoCD template consumes both `$CLUSTER_NAME/nautobot-target-proxy/values.yaml` and the matching component directory as its second source, so you can keep simple configuration in values and reserve the overlay for Kubernetes-native additions.
