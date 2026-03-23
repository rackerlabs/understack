---
charts:
- gateway-helm
kustomize_paths:
- components/envoy-gateway
deploy_overrides:
  helm:
    mode: values
  kustomize:
    mode: second_source
---

# envoy-gateway

Envoy Gateway installation plus any deploy-specific gateway-class resources.

## Deployment Scope

- Cluster scope: global or site
- Values keys: `global.envoy_gateway`, `site.envoy_gateway`
- ArgoCD Application template: `charts/argocd-understack/templates/application-envoy-gateway.yaml`

## How ArgoCD Builds It

{{ component_argocd_builds() }}

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
global:
  envoy_gateway:
    enabled: true
site:
  envoy_gateway:
    enabled: true
```

## Deployment Repo Content

{{ secrets_disclaimer }}

Required or commonly required items:

- `values.yaml`: Provide the Helm values that tune the gateway controller for your environment.

Optional additions:

- `GatewayClass manifest`: Add a GatewayClass if you need an explicit class name, controller parameters, or multiple gateway classes in the same cluster.
- `Additional Gateway API resources`: Place environment-specific gateway bootstrap objects in this overlay if they must be applied with the controller.
