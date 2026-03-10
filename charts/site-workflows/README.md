# Site Workflows Helm Chart

This Helm chart deploys Argo Events sensors and eventsources for UnderStack services.

## Features

- Conditional deployment of OpenStack service integrations (Cinder, Ironic, Keystone, Neutron, Nova)
- EventBus configuration for Argo Events
- Service accounts for workflow execution
- RabbitMQ user and permission management
- Event-driven workflow automation

## Configuration

### Enabling/Disabling Services

Each OpenStack service can be independently enabled or disabled:

```yaml
enabled:
  cinder: true
  ironic: true
  keystone: true
  neutron: true
  nova: true
```

When a service is disabled, all related resources are excluded:

- EventSource
- RabbitMQ User and Permissions
- All Sensors that depend on that EventSource

### Additional Components

```yaml
eventbus:
  enabled: true

serviceAccounts:
  enabled: true

k8sSecretsEventSource:
  enabled: true
```
