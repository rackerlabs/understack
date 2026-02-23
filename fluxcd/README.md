# FluxCD Deployment for UnderStack

A Helm chart that generates FluxCD resources to deploy UnderStack on Kubernetes.

## Overview

This chart replaces the ArgoCD-based deployment with FluxCD resources. It generates:
- `GitRepository` resources for the UnderStack and deploy repositories
- `HelmRepository` resources for all required Helm charts
- `HelmRelease` resources for each component
- `Kustomization` resources for Kustomize-based components
- Namespace definitions

## Prerequisites

- Kubernetes cluster 1.24+
- FluxCD v2.0+ installed
- Helm 3.8+

## Installation

### 1. Install FluxCD

If FluxCD is not already installed:

```bash
# Install FluxCD controllers
flux install --version=2.4.0

# Or using Helm
helm repo add fluxcd https://fluxcd-community.github.io/helm-charts
helm install fluxcd fluxcd/flux2 \
  --namespace flux-system \
  --create-namespace
```

### 2. Create Git Credentials Secret

For private repositories, create a Kubernetes secret with your Git credentials:

```bash
# For HTTPS
kubectl create secret generic fluxcd-git-credentials \
  --namespace flux-system \
  --from-literal=username=your-username \
  --from-literal=password=your-token

# For SSH, create your own SSH key and add the public key to your Git provider
```

### 3. Deploy Using Helm

```bash
# Add the chart repository
helm repo add understack https://rackerlabs.github.io/understack

# Or use local chart
helm install understack ./fluxcd \
  --namespace flux-system \
  --create-namespace \
  --set cluster_server=https://kubernetes.default.svc \
  --set understack_url=https://github.com/rackerlabs/understack.git \
  --set deploy_url=https://github.com/your-org/your-deploy-repo.git \
  --set deploy_ref=main
```

## Configuration

### Required Values

| Value | Description | Example |
|-------|-------------|---------|
| `cluster_server` | Kubernetes API server URL | `https://kubernetes.default.svc` |
| `understack_url` | UnderStack repository URL | `https://github.com/rackerlabs/understack.git` |
| `deploy_url` | Deploy repository URL | `https://github.com/org/deploy.git` |
| `deploy_ref` | Deploy repository ref | `main`, `v1.0.0` |

### Optional Values

| Value | Default | Description |
|-------|---------|-------------|
| `deploy_path_prefix` | `""` | Prefix for deploy repo paths |
| `sync.prune` | `true` | Remove resources no longer in Git |
| `sync.selfHeal` | `true` | Reconcile drift automatically |
| `sync.createNamespace` | `true` | Create namespaces if missing |

### Global Components

Disable global components using:

```yaml
global:
  enabled: true
  cert_manager:
    enabled: false
  monitoring:
    enabled: false
  # ... other components
```

### Site Components

Disable site-specific components using:

```yaml
site:
  enabled: true
  keystone:
    enabled: false
  nova:
    enabled: false
  # ... other components
```

## Quick Start Example

```bash
# Deploy with all defaults
helm install understack ./fluxcd \
  --namespace flux-system \
  --create-namespace \
  --set cluster_server=https://kubernetes.default.svc \
  --set understack_url=https://github.com/rackerlabs/understack.git \
  --set understack_ref=main \
  --set deploy_url=https://github.com/myorg/my-deploy-repo.git \
  --set deploy_ref=main

# Upgrade
helm upgrade understack ./fluxcd \
  --namespace flux-system \
  --set deploy_ref=v1.2.0

# View status
flux get all --all-namespaces

# Check specific resource
flux get helmreleases -n monitoring
```

## Troubleshooting

### View Logs

```bash
# FluxCD controller logs
kubectl logs -n flux-system -l app.kubernetes.io/name=source-controller
kubectl logs -n flux-system -l app.kubernetes.io/name=helm-controller

# Specific HelmRelease
kubectl logs -n <namespace> -l app.kubernetes.io/name=<release-name>
```

### Common Issues

1. **HelmRelease stuck**: Check `kubectl describe helmrelease <name> -n <namespace>`
2. **Values not applied**: Ensure values files exist in the referenced paths
3. **Dependencies not ready**: Check `dependsOn` field and ensure prerequisites are deployed

### Force Reconcile

```bash
flux reconcile helmrelease <name> -n <namespace>
flux reconcile source git <repo-name>
```

## Directory Structure

```
fluxcd/
├── Chart.yaml              # Chart definition
├── values.yaml            # Default configuration
└── templates/
    ├── _helpers.tpl       # Helper functions
    ├── gitrepository*.tpl # GitRepository definitions
    ├── helmrepository.tpl # HelmRepository definitions
    ├── namespace.tpl      # Namespace definitions
    ├── root-kustomization.yaml.tpl
    ├── global/            # Global components
    ├── operators/        # Operator components
    ├── openstack/        # OpenStack services
    └── site/             # Site-specific components
```

## Upgrading

When upgrading the chart:

```bash
helm repo update
helm upgrade understack understack/fluxcd \
  --namespace flux-system \
  --set deploy_ref=main
```

FluxCD will automatically detect changes and reconcile.

## Uninstalling

```bash
# This will remove all FluxCD resources
helm uninstall understack -n flux-system
```
