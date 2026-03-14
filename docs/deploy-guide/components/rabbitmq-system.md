# rabbitmq-system

RabbitMQ cluster operator installation.

## Deployment Scope

- Cluster scope: global or site
- Values keys: `global.rabbitmq_system`, `site.rabbitmq_system`
- ArgoCD Application template: `charts/argocd-understack/templates/application-rabbitmq-system.yaml`

## How ArgoCD Builds It

- ArgoCD renders Kustomize path `operators/rabbitmq-system`.
- The current template does not read a deploy-repo `values.yaml` for this component.
- The current template does not apply a deploy-repo overlay directory for this component.

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
global:
  rabbitmq_system:
    enabled: true
site:
  rabbitmq_system:
    enabled: true
```

## Notes

- The current ArgoCD template deploys the shared operator manifests directly and does not consume deploy-repo values or overlay manifests for this component.
- Per-application RabbitMQ user Secrets belong with the consuming services such as Nova, Neutron, Glance, or Ironic.
