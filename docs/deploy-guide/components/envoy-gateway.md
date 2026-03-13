# envoy-gateway

Envoy Gateway installation plus any deploy-specific gateway-class resources.

## Deployment Scope

- Cluster scope: global or site
- Values keys: `global.envoy_gateway`, `site.envoy_gateway`
- ArgoCD Application template: `charts/argocd-understack/templates/application-envoy-gateway.yaml`

## How ArgoCD Builds It

- ArgoCD renders Helm chart `gateway-helm`, Kustomize path `components/envoy-gateway`.
- The deploy repo contributes `values.yaml` for this component.
- The deploy repo overlay directory for this component is applied as a second source, so `kustomization.yaml` and any referenced manifests are part of the final Application.

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

Use any secret delivery mechanism you prefer. The contract that matters is the final Kubernetes Secret or manifest shape described below.

Required or commonly required items:

- `values.yaml`: Provide the Helm values that tune the gateway controller for your environment.

Optional additions:

- `GatewayClass manifest`: Add a GatewayClass if you need an explicit class name, controller parameters, or multiple gateway classes in the same cluster.
- `Additional Gateway API resources`: Place environment-specific gateway bootstrap objects in this overlay if they must be applied with the controller.
