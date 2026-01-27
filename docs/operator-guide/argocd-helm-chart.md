# ArgoCD Application Management with Helm

UnderStack provides a Helm chart (`argocd-understack`) that generates ArgoCD
Applications for deploying all UnderStack components. This approach provides
several advantages over ApplicationSets:

- **Per-cluster version pinning**: Pin UnderStack to specific versions per cluster
- **Explicit component control**: Enable/disable components via values.yaml
- **Easier debugging**: Use `helm template` to preview generated Applications
- **Simpler mental model**: Standard Helm values instead of ApplicationSet generators

## Chart Overview

The chart is located at `charts/argocd-understack/` and generates ArgoCD
Application resources for:

- **Infrastructure**: cert-manager, cilium, envoy-gateway, sealed-secrets, etc.
- **Operators**: CNPG, external-secrets, mariadb-operator, rabbitmq, rook, etc.
- **OpenStack**: keystone, glance, nova, neutron, ironic, etc.
- **Site Services**: argo-workflows, chrony, undersync, monitoring, etc.
- **Global Services**: dex, nautobot, nautobotop, etc.

## Configuration

### Basic Structure

Each cluster requires a values file:

```yaml
# Required: Cluster server URL
cluster_server: https://kubernetes.default.svc

# UnderStack repository settings
understack_url: https://github.com/rackerlabs/understack.git
understack_ref: v1.0.0  # Pin to specific version

# Deployment repository (required)
deploy_url: https://github.com/your-org/deploy.git
deploy_ref: HEAD

# Optional: prefix for deploy repo path structure
# deploy_path_prefix: sites  # Results in "sites/<cluster-name>/..."

# Cluster type configuration
global:
  enabled: false  # Set true for global clusters

site:
  enabled: true   # Set true for site clusters
```

### Enabling/Disabling Components

Components can be enabled or disabled individually:

```yaml
site:
  enabled: true

  # Disable a component
  octavia:
    enabled: false

  # Enable with version override
  keystone:
    enabled: true
    chartVersion: "2025.2.6+9b270fe35"
```

### Deploy Repository Path Prefix

By default, the chart looks for cluster configs at `<Release.Name>/helm-configs/`
and `<Release.Name>/manifests/`. Use `deploy_path_prefix` to add a prefix:

```yaml
deploy_path_prefix: sites  # Results in "sites/my-cluster/helm-configs/..."
```

**Default structure:**

```text
deploy-repo/
├── uc-iad3-prod/
│   ├── helm-configs/
│   │   ├── keystone.yaml
│   │   └── ...
│   └── manifests/
│       └── ...
└── uc-ord1-staging/
    └── ...
```

**With `deploy_path_prefix: sites`:**

```text
deploy-repo/
├── sites/
│   ├── uc-iad3-prod/
│   │   ├── helm-configs/
│   │   └── manifests/
│   └── uc-ord1-staging/
│       └── ...
└── other-stuff/
    └── ...
```

### OpenStack Chart Versions

OpenStack services can have their chart versions pinned:

```yaml
site:
  keystone:
    chartVersion: "2025.2.6+9b270fe35"
  glance:
    chartVersion: "2025.2.6+9b270fe35"
  nova:
    chartVersion: "2025.1.19+12458c92d"
```

## Deployment

### App-of-Apps Pattern

Deploy the chart as an ArgoCD Application from the OCI registry:

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

For testing unreleased changes, reference the chart directly from git:

```yaml
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
```

### Preview Generated Applications

Before deploying, preview what Applications will be created:

```bash
helm template argocd-understack charts/argocd-understack \
  -f path/to/cluster-values.yaml
```

## Cluster Types

### Global Cluster

A global cluster hosts shared services like Nautobot and Dex:

```yaml
understack_ref: v1.0.0
deploy_url: https://github.com/your-org/deploy.git

global:
  enabled: true
  nautobot:
    enabled: true
  dex:
    enabled: true
  nautobotop:
    enabled: true

site:
  enabled: false
```

### Site Cluster

A site cluster runs OpenStack and site-specific services:

```yaml
understack_ref: v1.0.0
deploy_url: https://github.com/your-org/deploy.git

global:
  enabled: false

site:
  enabled: true
  keystone:
    enabled: true
  nova:
    enabled: true
  ironic:
    enabled: true
```

### All-in-One (AIO) Cluster

An AIO cluster runs both global and site services:

```yaml
understack_ref: v1.0.0
deploy_url: https://github.com/your-org/deploy.git

global:
  enabled: true

site:
  enabled: true
```

## ArgoCD Projects

Applications are organized into three ArgoCD projects:

| Project | Purpose | Components |
|---------|---------|------------|
| `understack` | Main project | OpenStack services, workflows, dex, nautobot |
| `understack-infra` | Infrastructure | Cilium, cert-manager, ingress-nginx, sealed-secrets |
| `understack-operators` | Operators | CNPG, MariaDB, External Secrets, RabbitMQ, monitoring |

## Sync Policies

The chart configures appropriate sync policies for each component type:

| Component Type | ServerSideApply | ApplyOutOfSyncOnly |
|---------------|-----------------|-------------------|
| Infrastructure | true | true |
| Operators | true | true |
| OpenStack | false | true |
| Site Services | true | true |

OpenStack uses `ServerSideApply=false` due to compatibility requirements
with Helm hooks that use `force=true`.

## Troubleshooting

### View Application Status

```bash
# List all applications
kubectl get applications -n argocd

# Watch for changes
kubectl get applications -n argocd -w

# Use ArgoCD CLI
argocd app list --grpc-web
```

### Check Application Details

```bash
# Kubernetes describe
kubectl describe application <app-name> -n argocd

# ArgoCD CLI with sync status
argocd app get <app-name> --grpc-web
```

### Compare Generated vs Deployed

```bash
# Generate expected Applications
helm template my-cluster charts/argocd-understack \
  -f cluster-values.yaml > expected.yaml

# Get current Applications
kubectl get applications -n argocd -o yaml > current.yaml

# Compare
diff expected.yaml current.yaml
```

### Application Not Creating

1. Check the bootstrap Application status:

   ```bash
   kubectl describe application argocd-understack -n argocd
   ```

2. Verify values file is accessible and valid:

   ```bash
   helm template test charts/argocd-understack -f your-values.yaml
   ```

3. Check ArgoCD logs:

   ```bash
   kubectl logs -n argocd -l app.kubernetes.io/name=argocd-application-controller
   ```

### Sync Errors

1. Check Application sync status:

   ```bash
   argocd app get <app-name> --grpc-web
   ```

2. Review sync options - ensure correct `ServerSideApply` setting:
   - OpenStack services: `ServerSideApply=false`
   - Other components: `ServerSideApply=true`

3. Check for resource conflicts:

   ```bash
   kubectl get application <app-name> -n argocd -o jsonpath='{.status.conditions}'
   ```

### Component Not Appearing

1. Verify component is enabled in values:

   ```yaml
   site:
     your_component:
       enabled: true
   ```

2. Check correct scope (`global` vs `site`) - some components exist in both

3. Preview what the chart generates:

   ```bash
   helm template my-cluster charts/argocd-understack \
     -f values.yaml | grep -A5 "name: my-cluster-your-component"
   ```

### Resources Not Updating

1. Check if `ApplyOutOfSyncOnly=true` is preventing updates:

   ```bash
   # Force a sync
   argocd app sync <app-name> --grpc-web
   ```

2. Verify the source revision is correct:

   ```bash
   kubectl get application <app-name> -n argocd \
     -o jsonpath='{.spec.source.targetRevision}'
   ```

### Debugging Helm Values

1. Check what values ArgoCD resolved:

   ```bash
   argocd app manifests <app-name> --grpc-web | head -100
   ```

2. Verify value file paths are correct (check for typos in `$deploy/` paths)

3. Test locally:

   ```bash
   helm template test charts/argocd-understack \
     -f values.yaml --debug
   ```

## Values Reference

See the full values.yaml in the chart for all available options:

```bash
helm show values charts/argocd-understack
```

Key sections:

- `cluster_server`: Target Kubernetes API server URL
- `understack_url`, `understack_ref`: UnderStack repository and version
- `deploy_url`, `deploy_ref`: Deployment repository and version
- `deploy_path_prefix`: Optional path prefix for deploy repo structure
- `global.*`: Global cluster components (nautobot, dex, etc.)
- `site.*`: Site cluster components (OpenStack, workflows, etc.)
- `site.openstack.*`: OpenStack-specific settings (namespace, repoUrl)
- `site.<service>.chartVersion`: Pin specific chart versions
