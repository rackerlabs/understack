# nautobotop

Global Nautobot operator deployment driven from the deploy repo.

## Deployment Scope

- Cluster scope: global
- Values key: `global.nautobotop`
- ArgoCD Application template: `charts/argocd-understack/templates/application-nautobotop.yaml`

## How ArgoCD Builds It

- ArgoCD renders Helm chart `nautobotop`.
- The deploy repo contributes `values.yaml` for this component.
- The deploy repo overlay directory for this component is applied as a second source, so `kustomization.yaml` and any referenced manifests are part of the final Application.

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
global:
  nautobotop:
    enabled: true
```

## Deployment Repo Content

Use any secret delivery mechanism you prefer. The contract that matters is the final Kubernetes Secret or manifest shape described below.

Required or commonly required items:

- `values.yaml`: Provide the Helm values for the operator itself.
- `Operator custom resource`: Add the `Nautobot` custom resource that declares the instance the operator should manage.
- `nautobot-token` Secret: Provide `username`, `token`, and `hostname` so the operator or helper jobs can call the source-of-truth API.

Optional additions:

- `Additional operator-managed objects`: Add extra custom resources here if you run more than one operator-managed Nautobot workload.
