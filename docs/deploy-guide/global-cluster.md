# Deploying a Global Cluster

The [Global cluster](./welcome.md#system-division) hosts shared services
that exist once per partition, such as [Nautobot][nautobot] (DCIM/IPAM),
[Dex][dex] (SSO/OIDC), and global workflows. This guide walks through
setting up a Global cluster from scratch using an incremental approach:
start with everything disabled, verify ArgoCD connectivity, then enable
components one at a time.

## Prerequisites

Before starting, ensure:

- You have a running [Management cluster](./management-cluster.md) with
  ArgoCD deployed
- You have a [deployment repository](./deploy-repo.md) initialized
- Your target Kubernetes cluster has a **CNI** (e.g., Cilium) configured
  and operational
- Your target Kubernetes cluster has a **storage provisioner** configured
  and operational

## Create the Cluster Directory

In your deployment repository, create a directory named after your cluster.
This name must match the cluster name registered in ArgoCD.

```bash title="From the deploy repo root"
mkdir -p my-global/{manifests,helm-configs}
```

## Create the Initial deploy.yaml

Create a `deploy.yaml` in your cluster directory. This file combines the
repository metadata and the Helm values for the
[argocd-understack][argocd-helm-chart] chart into a single
file.

Start with **everything disabled** so you can verify ArgoCD connectivity
before deploying any workloads.

```yaml title="my-global/deploy.yaml"
---
understack_url: https://github.com/rackerlabs/understack.git
understack_ref: v0.1.0  # replace with the tag or git reference you want to use
deploy_url: https://github.com/my-org/my-deploy.git
deploy_ref: HEAD

global:
  enabled: false

site:
  enabled: false
```

## Register the Cluster with ArgoCD

Your Global cluster must be registered as a cluster in ArgoCD on the
Management cluster. See [Management Cluster](./management-cluster.md#configuring-your-global-andor-site-cluster-in-argocd)
for details on creating the cluster secret.

When creating your cluster secret, set the role annotation to `global`:

```yaml
metadata:
  annotations:
    understack.rackspace.com/role: global
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
kubectl get applications -n argocd | grep my-global
```

## Enable Components

With ArgoCD connectivity confirmed, you can begin enabling components one
at a time. After enabling each component, commit and push your changes,
then verify the ArgoCD Application becomes healthy before moving on.

### cert-manager

[cert-manager][cert-manager] provides TLS certificate management. Enable
it in your `deploy.yaml` and provide your ClusterIssuer manifests.

```yaml title="my-global/deploy.yaml (update)"
global:
  enabled: true

  cert_manager:
    enabled: true
```

Create a directory for your cluster issuer manifests:

```bash
mkdir -p my-global/manifests/cert-manager
```

Place your `ClusterIssuer` resource(s) in this directory. These define how
certificates will be issued for services in your cluster.

### External DNS

[External DNS][external-dns] automates DNS record management for services.

```yaml title="my-global/deploy.yaml (update)"
global:
  # ...
  external_dns:
    enabled: true
```

### Dex

[Dex][dex] provides OIDC-based SSO across UnderStack services. Dex
requires both Helm value overrides and manifests.

```yaml title="my-global/deploy.yaml (update)"
global:
  # ...
  dex:
    enabled: true
```

Create the manifests directory and Helm values file:

```bash
mkdir -p my-global/manifests/dex
```

Configure your authentication in the Helm values file:

```yaml title="my-global/helm-configs/dex.yaml"
# See the Dex configuration guide for details on what goes here
```

For details on configuring Dex authentication, see
[Configuring Dex](./config-dex.md) and [Authentication](./auth.md).

## Next Steps

Continue enabling components in your `deploy.yaml` as needed. The full
list of available global components and their defaults can be found in the
[argocd-understack values.yaml][values] or the
[ArgoCD Helm Chart guide](../operator-guide/argocd-helm-chart.md).

A typical global cluster will eventually enable most or all of the
following:

| Component | Purpose |
|---|---|
| `cert_manager` | TLS certificate management |
| `cilium` | CNI network policies |
| `cnpg_system` | Cloud Native PostgreSQL operator |
| `dex` | SSO/OIDC provider |
| `envoy_gateway` | API gateway |
| `etcdbackup` | etcd backup |
| `external_dns` | DNS record automation |
| `external_secrets` | Secrets management |
| `global_workflows` | Argo Events and Workflows |
| `ingress_nginx` | Ingress controller |
| `monitoring` | Prometheus/Grafana monitoring |
| `nautobot` | Network Source of Truth |
| `nautobotop` | Nautobot Kubernetes operator |
| `openebs` | Storage (if using OpenEBS) |
| `openstack_resource_controller` | OpenStack resource operator |
| `opentelemetry_operator` | OpenTelemetry operator |
| `otel_collector` | Observability collector |
| `rabbitmq_system` | RabbitMQ operator |
| `rook` | Storage (if using Rook/Ceph) |
| `sealed_secrets` | Sealed Secrets operator |
| `understack_cluster_issuer` | UnderStack cert-manager ClusterIssuer |

For each component that requires environment-specific configuration, you
can provide:

- **Helm value overrides** in `my-global/helm-configs/<component>.yaml`
- **Kustomize manifests** in `my-global/manifests/<component>/`

See [Configuring Components](./component-config.md) for details on these
customization methods.

[nautobot]: <https://docs.nautobot.com/>
[dex]: <https://dexidp.io/>
[cert-manager]: <https://cert-manager.io/>
[external-dns]: <https://kubernetes-sigs.github.io/external-dns/>
[argocd-helm-chart]: <../operator-guide/argocd-helm-chart.md>
[values]: <https://github.com/rackerlabs/understack/blob/main/charts/argocd-understack/values.yaml>
