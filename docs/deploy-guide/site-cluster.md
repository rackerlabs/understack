# Deploying a Site Cluster

A [Site cluster](./welcome.md#system-division) runs the OpenStack services
and automation workflows that manage bare metal hardware. Each site cluster
is associated with a [Global cluster](./global-cluster.md) in the same
partition and relies on it for shared services like [Nautobot][nautobot]
and [Dex][dex]. This guide walks through setting up a Site cluster from
scratch using an incremental approach: start with everything disabled,
verify ArgoCD connectivity, then enable components one at a time.

## Prerequisites

Before starting, ensure:

- You have a running [Management cluster](./management-cluster.md) with
  ArgoCD deployed
- You have a [Global cluster](./global-cluster.md) deployed and healthy
  in the same partition
- You have a [deployment repository](./deploy-repo.md) initialized
- Your target Kubernetes cluster has a **CNI** (e.g., Cilium) configured
  and operational
- Your target Kubernetes cluster has a **storage provisioner** configured
  and operational

## Create the Initial Configuration

Initialize your site cluster configuration using `understackctl`:

```bash
cd /path/to/deploy-repo
understackctl deploy init my-site --type site
```

This creates `my-site/deploy.yaml` with all site components enabled:

```yaml title="my-site/deploy.yaml"
understack_url: https://github.com/rackerlabs/understack.git
deploy_url: https://github.com/my-org/my-deploy.git
site:
  enabled: true
  keystone:
    enabled: true
  nova:
    enabled: true
  neutron:
    enabled: true
  ironic:
    enabled: true
  # ... additional site components
```

To start with everything disabled for initial ArgoCD connectivity testing,
edit the file to set `enabled: false`:

```yaml
site:
  enabled: false
```

Create the manifest directories:

```bash
understackctl deploy update my-site
```

## Register the Cluster with ArgoCD

Your Site cluster must be registered as a cluster in ArgoCD on the
Management cluster. See [Management Cluster](./management-cluster.md#configuring-your-global-andor-site-cluster-in-argocd)
for details on creating the cluster secret.

When creating your cluster secret, set the role annotation to `site`:

```yaml
metadata:
  annotations:
    understack.rackspace.com/role: site
```

!!! note "TODO"
    Detailed end-to-end cluster registration documentation is a work in
    progress. For now, refer to the
    [Management Cluster](./management-cluster.md) and
    [ArgoCD Helm Chart](../operator-guide/argocd-helm-chart.md)
    documentation.

## Verify ArgoCD Connectivity

Once the cluster is registered, commit and push your deploy repo changes.
Verify that ArgoCD can see your cluster and that the application is healthy
(even though nothing is deployed yet).

```bash
# on the management cluster
kubectl get applications -n argocd | grep my-site
```

## Enable Components

With ArgoCD connectivity confirmed, you can begin enabling components one
at a time. After enabling each component, commit and push your changes,
then verify the ArgoCD Application becomes healthy before moving on.

Site clusters have more components than global clusters. The sections
below are organized in a recommended deployment order, following the
sync wave ordering used by ArgoCD.

### Infrastructure Foundation

These components provide the base platform that all other services depend
on. Enable them first.

#### cert-manager

```yaml title="my-site/deploy.yaml (update)"
site:
  enabled: true

  cert_manager:
    enabled: true
```

After enabling, run `understackctl deploy update my-site` to create the
component directory. Then place your `ClusterIssuer` resource(s) in
`my-site/cert-manager/`.

#### External DNS

```yaml title="my-site/deploy.yaml (update)"
site:
  # ...
  external_dns:
    enabled: true
```

#### External Secrets

```yaml title="my-site/deploy.yaml (update)"
site:
  # ...
  external_secrets:
    enabled: true
```

See [External Secrets Operator Setup](./secrets-eso-setup.md) for
configuring your secret store.

#### Sealed Secrets

```yaml title="my-site/deploy.yaml (update)"
site:
  # ...
  sealed_secrets:
    enabled: true
```

### Operators

These operators manage stateful services used by OpenStack.

#### MariaDB Operator

The MariaDB operator manages database instances for OpenStack services.

```yaml title="my-site/deploy.yaml (update)"
site:
  # ...
  mariadb_operator:
    enabled: true
```

#### RabbitMQ Operator

The RabbitMQ operator manages message broker instances for OpenStack
inter-service communication.

```yaml title="my-site/deploy.yaml (update)"
site:
  # ...
  rabbitmq_system:
    enabled: true
```

### OpenStack Shared Infrastructure

Before deploying individual OpenStack services, enable the shared
infrastructure that they depend on.

#### OpenStack Base

The `openstack` component creates shared resources: MariaDB cluster,
RabbitMQ cluster, secrets, and service accounts.

```yaml title="my-site/deploy.yaml (update)"
site:
  # ...
  openstack:
    enabled: true
```

Configure the shared OpenStack infrastructure in your Helm values.
After enabling the component, run `understackctl deploy update my-site` to
create the directory, then edit `my-site/openstack/values.yaml`.

See [Configuring OpenStack (Shared)](./config-openstack.md) for details on
MariaDB, RabbitMQ, and service account configuration.

#### Memcached

```yaml title="my-site/deploy.yaml (update)"
site:
  # ...
  openstack_memcached:
    enabled: true
```

### OpenStack Services - Wave 1 (Identity)

#### Keystone

Keystone is the identity service and must be deployed before all other
OpenStack services.

```yaml title="my-site/deploy.yaml (update)"
site:
  # ...
  keystone:
    enabled: true
```

After enabling, run `understackctl deploy update my-site` to create the
directory. Provide any Helm value overrides in
`my-site/keystone/values.yaml`.

### OpenStack Services - Wave 2 (Core Services)

These services can be enabled together once Keystone is healthy.

#### Glance (Image Service)

```yaml title="my-site/deploy.yaml (update)"
site:
  # ...
  glance:
    enabled: true
```

#### Placement

```yaml title="my-site/deploy.yaml (update)"
site:
  # ...
  placement:
    enabled: true
```

#### Neutron (Networking)

```yaml title="my-site/deploy.yaml (update)"
site:
  # ...
  neutron:
    enabled: true
```

#### Ironic (Bare Metal)

```yaml title="my-site/deploy.yaml (update)"
site:
  # ...
  ironic:
    enabled: true
```

#### Cinder (Block Storage)

```yaml title="my-site/deploy.yaml (update)"
site:
  # ...
  cinder:
    enabled: true
```

### Networking

#### Open vSwitch

```yaml title="my-site/deploy.yaml (update)"
site:
  # ...
  openvswitch:
    enabled: true
```

#### OVN (Open Virtual Network)

```yaml title="my-site/deploy.yaml (update)"
site:
  # ...
  ovn:
    enabled: true
```

### OpenStack Services - Wave 3 (Compute and Load Balancing)

These services depend on the wave 2 services.

#### Nova (Compute)

```yaml title="my-site/deploy.yaml (update)"
site:
  # ...
  nova:
    enabled: true
```

#### Octavia (Load Balancer)

```yaml title="my-site/deploy.yaml (update)"
site:
  # ...
  octavia:
    enabled: true
```

### OpenStack Services - Wave 4 (Dashboards)

#### Horizon

```yaml title="my-site/deploy.yaml (update)"
site:
  # ...
  horizon:
    enabled: true
```

#### Skyline

```yaml title="my-site/deploy.yaml (update)"
site:
  # ...
  skyline:
    enabled: true
```

### Workflows and Automation

#### Argo Events and Workflows

```yaml title="my-site/deploy.yaml (update)"
site:
  # ...
  argo_events:
    enabled: true
  argo_workflows:
    enabled: true
```

See [Configuring Argo Workflows](./config-argo-workflows.md) for SSO
and Ingress setup.

#### Site Workflows

Site workflows implement the event-driven automation for bare metal
lifecycle management.

```yaml title="my-site/deploy.yaml (update)"
site:
  # ...
  site_workflows:
    enabled: true
```

### Remaining Components

Enable these as needed for your deployment.

| Component | `deploy.yaml` key | Purpose |
|---|---|---|
| Cilium configs | `site.cilium` | CNI network policies |
| Chrony | `site.chrony` | NTP time synchronization |
| Envoy Gateway | `site.envoy_gateway` | API gateway |
| Envoy configs | `site.envoy_configs` | Gateway routes and policies |
| etcd backup | `site.etcdbackup` | etcd backup |
| Monitoring | `site.monitoring` | Prometheus/Grafana |
| Nautobot site | `site.nautobot_site` | Site-specific Nautobot resources |
| OpenEBS | `site.openebs` | Storage (if using OpenEBS) |
| OpenStack exporter | `site.openstack_exporter` | Prometheus metrics for OpenStack |
| OpenStack Resource Controller | `site.openstack_resource_controller` | OpenStack resource operator |
| OpenTelemetry operator | `site.opentelemetry_operator` | OpenTelemetry operator |
| OTel collector | `site.otel_collector` | Observability collector |
| Rook | `site.rook` | Storage (if using Rook/Ceph) |
| SNMP exporter | `site.snmp_exporter` | Network device monitoring |
| UnderStack cluster issuer | `site.understack_cluster_issuer` | cert-manager ClusterIssuer |
| Undersync | `site.undersync` | Synchronization service |

## Customizing Components

For each component that requires environment-specific configuration, you
can provide:

- **Helm value overrides** in `my-site/<component>/values.yaml`
- **Kustomize manifests** in `my-site/<component>/`

See [Configuring Components](./component-config.md) for details on these
customization methods.

## Related Documentation

- [Configuring OpenStack (Shared)](./config-openstack.md) - MariaDB,
  RabbitMQ, and service account setup
- [External Secrets Operator Setup](./secrets-eso-setup.md) - Secret
  store configuration
- [Configuring Dex](./config-dex.md) - SSO/OIDC (on the Global cluster)
- [Authentication](./auth.md) - Authentication configuration
- [Configuring Argo Workflows](./config-argo-workflows.md) - Workflow
  SSO and Ingress
- [Override OpenStack Service Config](./override-openstack-svc-config.md) -
  Per-service configuration overrides

[nautobot]: <https://docs.nautobot.com/>
[dex]: <https://dexidp.io/>
