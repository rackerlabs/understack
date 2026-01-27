# argocd-understack

A Helm chart that generates ArgoCD Applications for deploying UnderStack components.

## Overview

This chart creates ArgoCD Application resources that deploy and manage all
UnderStack components. Instead of using ApplicationSets, this chart provides:

- **Per-cluster version pinning** via `understack_ref`
- **Explicit component enablement** via values.yaml
- **Easy debugging** with `helm template`
- **Standard Helm workflow** for configuration management

## Prerequisites

- Kubernetes cluster with ArgoCD installed
- ArgoCD projects configured: `understack`, `understack-infra`, `understack-operators`
- Access to UnderStack and deployment repositories

## Installation

### Using ArgoCD (Recommended)

Create an ArgoCD Application that deploys this chart from the OCI registry:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: argocd-understack
  namespace: argocd
spec:
  project: understack
  sources:
    - repoURL: ghcr.io/rackerlabs/understack
      chart: argocd-understack
      targetRevision: 0.1.0  # Chart version
      helm:
        releaseName: my-cluster-name
        valueFiles:
          - $deploy/my-cluster-name/argocd-understack-values.yaml
    - repoURL: https://github.com/your-org/deploy.git
      targetRevision: HEAD
      ref: deploy
  destination:
    server: https://kubernetes.default.svc
    namespace: argocd
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

### Using Git Repository (for development)

For testing unreleased changes, reference the chart directly from git:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: argocd-understack
  namespace: argocd
spec:
  project: understack
  sources:
    - repoURL: https://github.com/rackerlabs/understack.git
      targetRevision: feature-branch
      path: charts/argocd-understack
      helm:
        releaseName: my-cluster-name
        valueFiles:
          - $deploy/my-cluster-name/argocd-understack-values.yaml
    - repoURL: https://github.com/your-org/deploy.git
      targetRevision: HEAD
      ref: deploy
  destination:
    server: https://kubernetes.default.svc
    namespace: argocd
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

### Using Helm CLI

```bash
helm install argocd-understack oci://ghcr.io/rackerlabs/understack/argocd-understack \
  --version 0.1.0 \
  -n argocd \
  -f cluster-values.yaml
```

## Configuration

### Required Values

| Parameter | Description |
|-----------|-------------|
| `deploy_url` | URL to your deployment repository |

### Common Values

| Parameter | Description | Default |
|-----------|-------------|---------|
| `cluster_server` | Target Kubernetes API server | `https://kubernetes.default.svc` |
| `understack_url` | UnderStack repository URL | `https://github.com/rackerlabs/understack.git` |
| `understack_ref` | UnderStack git reference | `HEAD` |
| `deploy_ref` | Deployment repo git reference | `HEAD` |
| `global.enabled` | Enable global cluster components | `true` |
| `site.enabled` | Enable site cluster components | `true` |

### Example Values Files

**Site Cluster:**
```yaml
cluster_server: https://kubernetes.default.svc
understack_ref: v1.0.0
deploy_url: https://github.com/your-org/deploy.git

global:
  enabled: false

site:
  enabled: true
  octavia:
    enabled: false  # Disable specific component
```

**Global Cluster:**
```yaml
cluster_server: https://kubernetes.default.svc
understack_ref: v1.0.0
deploy_url: https://github.com/your-org/deploy.git

global:
  enabled: true

site:
  enabled: false
```

## Components

### Global Components

Components deployed on global clusters:

| Component | Values Key | Description |
|-----------|-----------|-------------|
| cert-manager | `global.cert_manager` | Certificate management |
| cilium | `global.cilium` | CNI networking |
| cnpg-system | `global.cnpg_system` | PostgreSQL operator |
| dex | `global.dex` | OIDC provider |
| envoy-gateway | `global.envoy_gateway` | API gateway |
| external-dns | `global.external_dns` | DNS management |
| external-secrets | `global.external_secrets` | Secret management |
| ingress-nginx | `global.ingress_nginx` | Ingress controller |
| monitoring | `global.monitoring` | Prometheus stack |
| nautobot | `global.nautobot` | Network source of truth |
| nautobotop | `global.nautobotop` | Nautobot operator |
| openstack-resource-controller | `global.openstack_resource_controller` | ORC operator |
| opentelemetry-operator | `global.opentelemetry_operator` | OTel operator |
| rabbitmq-system | `global.rabbitmq_system` | RabbitMQ operator |
| rook | `global.rook` | Ceph storage |
| sealed-secrets | `global.sealed_secrets` | Sealed secrets |

### Site Components

Components deployed on site clusters:

| Component | Values Key | Description |
|-----------|-----------|-------------|
| argo-events | `site.argo_events` | Event processing |
| argo-workflows | `site.argo_workflows` | Workflow engine |
| chrony | `site.chrony` | NTP service |
| envoy-configs | `site.envoy_configs` | Gateway configs |
| nautobot-site | `site.nautobot_site` | Site Nautobot config |
| openstack-exporter | `site.openstack_exporter` | Metrics exporter |
| openstack-memcached | `site.openstack_memcached` | Caching |
| site-workflows | `site.site_workflows` | Site workflows |
| snmp-exporter | `site.snmp_exporter` | SNMP metrics |
| undersync | `site.undersync` | Sync service |

### OpenStack Components

OpenStack services with configurable chart versions:

| Component | Values Key |
|-----------|-----------|
| keystone | `site.keystone` |
| glance | `site.glance` |
| cinder | `site.cinder` |
| ironic | `site.ironic` |
| neutron | `site.neutron` |
| placement | `site.placement` |
| nova | `site.nova` |
| octavia | `site.octavia` |
| horizon | `site.horizon` |
| skyline | `site.skyline` |
| openvswitch | `site.openvswitch` |
| ovn | `site.ovn` |

## Debugging

Preview generated Applications:

```bash
helm template argocd-understack ./charts/argocd-understack \
  -f cluster-values.yaml
```

Compare with deployed Applications:

```bash
# Generate expected
helm template argocd-understack ./charts/argocd-understack \
  -f cluster-values.yaml > expected.yaml

# Get current
kubectl get applications -n argocd -o yaml > current.yaml

# Compare
diff expected.yaml current.yaml
```

## Development

### Adding a New Component

1. Create template in `templates/application-<component>.yaml.tpl`
2. Add configuration to `values.yaml` under appropriate section
3. Update this README

### Template Pattern

```yaml
{{- if eq (include "understack.isEnabled" (list $.Values.site "component_name")) "true" }}
---
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: {{ printf "%s-%s" $.Release.Name "component-name" }}
  annotations:
    argocd.argoproj.io/compare-options: ServerSideDiff=true,IncludeMutationWebhook=true
spec:
  destination:
    namespace: component-namespace
    server: {{ $.Values.cluster_server }}
  project: understack
  sources:
  # ... sources configuration
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
    - CreateNamespace=true
    - ServerSideApply=true
    - RespectIgnoreDifferences=true
    - ApplyOutOfSyncOnly=true
{{- end }}
```

## License

Apache 2.0
