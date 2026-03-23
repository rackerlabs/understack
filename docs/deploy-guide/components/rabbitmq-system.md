---
kustomize_paths:
- operators/rabbitmq-system
deploy_overrides:
  helm:
    mode: none
  kustomize:
    mode: none
---

# rabbitmq-system

RabbitMQ cluster operator installation.

## Deployment Scope

- Cluster scope: global or site
- Values keys: `global.rabbitmq_system`, `site.rabbitmq_system`
- ArgoCD Application template: `charts/argocd-understack/templates/application-rabbitmq-system.yaml`

## How ArgoCD Builds It

{{ component_argocd_builds() }}

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

## Deployment Repo Content

{{ secrets_disclaimer }}

Required or commonly required items:

- None for this Application today. It deploys the shared operator manifests directly and does not consume deploy-repo values or overlay manifests for this component.

Optional additions:

- Per-application RabbitMQ user Secrets belong with the consuming services such as Nova, Neutron, Glance, or Ironic rather than here.
