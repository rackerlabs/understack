# Configuring OpenStack (Shared)

The `openstack` component provides shared infrastructure and prerequisites for all OpenStack services in UnderStack. This includes database, messaging, and common resources needed by individual OpenStack services like Keystone, Nova, Neutron, and Ironic.

## Overview

The OpenStack component is a Helm chart that creates:

- **MariaDB cluster** - Primary database for OpenStack services
- **RabbitMQ cluster** - Message broker for OpenStack communication
- **Shared secrets and credentials** - Common authentication resources
- **Kubernetes Service accounts** - Kubernetes RBAC for workflow automation
- **External secret stores** - Integration with external secret management

## Configuration

Configure the OpenStack component by editing `$DEPLOY_NAME/openstack/values.yaml` in your deployment repository.

### Basic Configuration

```yaml
# Required: OpenStack region name
regionName: "RegionOne"

# Optional: Keystone API URL (defaults to internal cluster service)
keystoneUrl: "http://keystone-api.openstack.svc.cluster.local:5000/v3"
```

### MariaDB Database Configuration

The MariaDB cluster provides the primary database for OpenStack services:

```yaml
mariadb:
  # Root password configuration
  rootPasswordSecretKeyRef:
    name: mariadb
    key: root-password
    generate: true  # Auto-generate if not provided

  # Storage configuration
  storage:
    size: 10Gi
    resizeInUseVolumes: true
    waitForVolumeResize: true
    volumeClaimTemplate:
      storageClassName: ceph-block-single
      accessModes:
        - ReadWriteOnce
      resources:
        requests:
          storage: 10Gi

  # Enable Galera cluster with 3 replicas for HA
  replicas: 3
```

#### Storage Considerations

- **Size**: Start with 10Gi minimum, scale based on your deployment size
- **Storage Class**: Use your cluster's high-performance storage class
- **Replicas**: 3 replicas provide high availability via Galera clustering
- **Resize**: Enable volume resizing for future scaling needs

### RabbitMQ Message Broker Configuration

RabbitMQ handles inter-service communication for OpenStack:

```yaml
rabbitmq:
  # Configure persistent storage for message queues
  persistence:
    enabled: true
    size: 8Gi
    storageClassName: ceph-block-single
```

### OpenStack Keystone Service Accounts

For production deployments, you can load service account credentials via the External Secrets Operator (ESO) instead of using OpenStack Helm's hardcoded credentials. This enables:

- **Secure credential management** from external secret stores (Vault, AWS Secrets Manager, etc.)
- **Multi-cluster deployments** where Keystone runs separately from other services
- **Credential isolation** for different [Sites](./welcome.md)

#### Basic ESO Configuration

Enable ESO integration in your `openstack.yaml`:

```yaml
keystoneServiceUsers:
  enabled: true
  secretStore:
    kind: "ClusterSecretStore"
    name: "openstack"
  keystoneInterface: "internal"
```

#### Service Account Setup

Each OpenStack service requires specific service accounts. At minimum, define `admin` and `user` accounts:

```yaml
keystoneServiceUsers:
  services:
    nova:
      - usage: admin
        remoteRef: "/openstack/admin-keystone-password"
      - usage: user
        remoteRef: "/openstack/nova-keystone-password"
    ironic:
      - usage: admin
        remoteRef: "/openstack/admin-keystone-password"
      - usage: user
        remoteRef: "/openstack/ironic-keystone-password"
```

**For complete ESO setup instructions, migration steps, and troubleshooting, see [External Secrets Operator Setup](./secrets-eso-setup.md).**

### Additional Kubernetes Resources

Use `extraObjects` to deploy additional Kubernetes manifests alongside the OpenStack component:

```yaml
extraObjects:
  - apiVersion: external-secrets.io/v1beta1
    kind: ExternalSecret
    metadata:
      name: openstack-credentials
    spec:
      secretStoreRef:
        kind: ClusterSecretStore
        name: vault-backend
      target:
        name: openstack-admin-credentials
      dataFrom:
        - extract:
            key: openstack/admin
```

## Integration with OpenStack Services

Individual OpenStack services (Keystone, Nova, Neutron, etc.) depend on resources created by this component:

- **Database**: Each service gets dedicated MariaDB databases
- **Messaging**: Services connect to the shared RabbitMQ cluster
- **Secrets**: Common credentials are managed centrally
- **Kubernetes Service Accounts**: Argo Workflows automation uses shared service accounts

## Security Considerations

### Secret Management

- Use External Secrets Operator for production deployments
- Rotate database and RabbitMQ credentials regularly
- Ensure proper RBAC for service accounts

### Network Security

- Configure network policies to restrict inter-pod communication
- Use TLS for all database and message broker connections
- Isolate OpenStack traffic using Kubernetes namespaces

## Monitoring and Observability

The OpenStack component integrates with cluster monitoring:

```yaml
# Enable monitoring for MariaDB
mariadb:
  metrics:
    enabled: true
    serviceMonitor:
      enabled: true

# Enable monitoring for RabbitMQ
rabbitmq:
  metrics:
    enabled: true
    serviceMonitor:
      enabled: true
```

## Troubleshooting

### Database Connection Issues

If OpenStack services can't connect to MariaDB:

1. Check MariaDB pod status: `kubectl get pods -l app=mariadb`
2. Verify service endpoints: `kubectl get endpoints mariadb`
3. Test connectivity from a service pod: `kubectl exec -it <pod> -- mysql -h mariadb -u root -p`

### Message Queue Problems

For RabbitMQ connectivity issues:

1. Check RabbitMQ cluster status: `kubectl exec -it rabbitmq-0 -- rabbitmqctl cluster_status`
2. Verify queue status: `kubectl exec -it rabbitmq-0 -- rabbitmqctl list_queues`
3. Check service connectivity: `kubectl get svc rabbitmq`

### Resource Scaling

To scale the database cluster:

```yaml
mariadb:
  replicas: 5  # Scale to 5 nodes
  storage:
    size: 50Gi  # Increase storage per node
```

Apply changes and monitor the scaling process:

```bash
kubectl get pods -l app=mariadb -w
```

## Related Documentation

- [External Secrets Operator Setup](./secrets-eso-setup.md) - Detailed ESO configuration for OpenStack service accounts
- [Component Configuration](./component-config.md) - General component configuration patterns
- [Override OpenStack Service Config](./override-openstack-svc-config.md) - Service-specific configuration overrides
- [Deploy Repo](./deploy-repo.md) - Deployment repository structure
