# FluxCD Deployment Quick Start

This guide provides a quick path to deploy UnderStack using FluxCD.

## Prerequisites

- Kubernetes cluster 1.24+
- kubectl configured
- Helm 3.8+
- Git repository for your overrides (deploy repo)

## Step 1: Install FluxCD

```bash
# Install FluxCD controllers
flux install --version=2.4.0
```

Or using Helm:

```bash
helm repo add fluxcd https://fluxcd-community.github.io/helm-charts
helm install fluxcd fluxcd/flux2 \
  --namespace flux-system \
  --create-namespace
```

## Step 2: Create Deploy Repository

Create a Git repository for your cluster-specific overrides:

```bash
# Clone your deploy repo
git clone https://github.com/your-org/your-deploy-repo.git
cd your-deploy-repo

# Create cluster directory
mkdir -p uc-iad3-prod
cat > uc-iad3-prod/apps.yaml << 'EOF'
components:
  octavia:
    enabled: false
EOF

# Commit and push
git add .
git commit -m "Initial deploy configuration"
git push
```

## Step 3: Deploy UnderStack

```bash
# Deploy using local chart
helm install understack ./fluxcd \
  --namespace flux-system \
  --create-namespace \
  --set cluster_server=https://kubernetes.default.svc \
  --set understack_url=https://github.com/rackerlabs/understack.git \
  --set understack_ref=main \
  --set deploy_url=https://github.com/your-org/your-deploy-repo.git \
  --set deploy_ref=main
```

## Step 4: Verify Deployment

```bash
# Check FluxCD status
flux get all --all-namespaces

# Check GitRepository
flux get sources git

# Check HelmReleases
flux get helmreleases --all-namespaces

# Watch progress
watch flux get helmreleases --all-namespaces
```

## Step 5: Common Operations

### Upgrade UnderStack

```bash
helm upgrade understack ./fluxcd \
  --namespace flux-system \
  --set deploy_ref=v1.2.0
```

### Disable a Component

Edit your deploy repo `apps.yaml`:

```yaml
components:
  octavia:
    enabled: false
  monitoring:
    enabled: false
```

Commit and push - FluxCD will automatically reconcile.

### Add Custom Values

Create `<component>/values.yaml` in your cluster folder:

```bash
mkdir -p uc-iad3-prod/dex
cat > uc-iad3-prod/dex/values.yaml << 'EOF'
config:
  issuer: https://dex.example.com
EOF

git add .
git commit -m "Add Dex configuration"
git push
```

## Monitoring

### View All Resources

```bash
# All FluxCD resources
flux get all --all-namespaces

# Specific namespace
flux get helmreleases -n monitoring
flux get kustomizations -n flux-system
```

### Check Logs

```bash
# Source controller
kubectl logs -n flux-system -l app.kubernetes.io/name=source-controller -f

# Helm controller
kubectl logs -n flux-system -l app.kubernetes.io/name=helm-controller -f
```

### Debug Issues

```bash
# Describe failing HelmRelease
kubectl describe helmrelease <name> -n <namespace>

# Get events
kubectl get events --sort-by='.lastTimestamp' | grep -i <release>
```

## Cleanup

```bash
# Uninstall UnderStack (keeps cluster resources)
helm uninstall understack -n flux-system

# Uninstall FluxCD
helm uninstall fluxcd -n flux-system
kubectl delete namespace flux-system
```

## Next Steps

- Read [README.md](README.md) for full configuration options
- Read [DEPLOY_REPO_OVERRIDES.md](DEPLOY_REPO_OVERRIDES.md) for override patterns
- Configure secrets using External Secrets Operator or Sealed Secrets
