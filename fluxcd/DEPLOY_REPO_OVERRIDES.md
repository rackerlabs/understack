# Deploy Repository Overrides

This document explains how to use a separate deploy repository to override UnderStack configurations per cluster.

## Overview

The FluxCD deployment supports cluster-specific overrides via a separate "deploy" repository. This allows you to:
- Keep the main UnderStack repository as a read-only upstream
- Store cluster-specific configurations in a separate repo
- Manage secrets and sensitive data separately

## How It Works

### Source Configuration

The chart references two Git repositories:

1. **understack_url**: Main UnderStack repository (read-only component definitions)
2. **deploy_url**: Your site-specific overrides repository

### Directory Structure

Your deploy repository should follow this pattern:

```
deploy-repo/
└── <release-name>/              # Must match Helm release name (e.g., uc-iad3-prod)
    ├── apps.yaml                 # Component enable/disable per cluster
    ├── cilium/
    │   └── values.yaml           # Cilium-specific config
    ├── dex/
    │   └── values.yaml           # Dex OIDC config
    ├── monitoring/
    │   └── values.yaml           # Prometheus rules, alert config
    ├── secret-openstack.yaml     # OpenStack secrets
    ├── cluster-issuer/
    │   └── cluster-issuer.yaml   # Cert-manager ClusterIssuer
    ├── keystone/
    │   └── values.yaml           # Keystone overrides
    ├── neutron/
    │   └── values.yaml
    └── nova/
        └── values.yaml
```

## Configuration Values

| Value | Description | Example |
|-------|-------------|---------|
| `deploy_url` | Git repo URL for overrides | `https://github.com/org/deploy.git` |
| `deploy_ref` | Git ref (branch/tag/commit) | `main`, `v1.0.0` |
| `deploy_path_prefix` | Optional path prefix | `sites` |

## Examples

### Example 1: Simple Per-Cluster Setup

**Deploy command:**
```bash
--release uc-iad3-prod \
--set deploy_url=https://github.com/org/prod-deploy.git \
--set deploy_ref=main
```

**Expected deploy repo structure:**
```
prod-deploy/
└── uc-iad3-prod/
    ├── apps.yaml
    ├── dex/
    │   └── values.yaml
    └── monitoring/
        └── values.yaml
```

### Example 2: Multiple Environments

**Production:**
```bash
--release uc-iad3-prod \
--set deploy_url=https://github.com/org/understack-deploy.git \
--set deploy_ref=main
```

**Staging:**
```bash
--release uc-iad3-staging \
--set deploy_url=https://github.com/org/understack-deploy.git \
--set deploy_ref=develop
```

Both clusters use the same deploy repo but different refs.

### Example 3: Using deploy_path_prefix

For repos with multiple clusters under a common prefix:

```bash
--set deploy_path_prefix=sites \
--set deploy_ref=main
```

**Expected deploy repo structure:**
```
deploy-repo/
└── sites/
    └── uc-iad3-prod/
        ├── apps.yaml
        └── dex/
            └── values.yaml
```

## Overriding Components

### Disable a Component

Create `apps.yaml` in your cluster folder:

```yaml
# uc-iad3-prod/apps.yaml
components:
  octavia:
    enabled: false
  monitoring:
    enabled: true
    # Custom values can be inline
    values:
      prometheus:
        retention: 30d
```

### Customize Helm Values

Create `<component>/values.yaml` in your cluster folder:

```yaml
# monitoring/values.yaml
prometheus:
  retention: 30d
  resources:
    requests:
      memory: 2Gi
      cpu: 1000m
  alertmanager:
    enabled: true
```

### Add Custom Resources

Create manifests in your cluster folder - they'll be applied via Kustomize overlays:

```yaml
# cluster-issuer/cluster-issuer.yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: admin@example.com
    privateKeySecretRef:
      name: letsencrypt-prod
    solvers:
      - http01:
          ingress:
            class: nginx
```

## Secrets Management

### Option 1: External Secrets Operator

Use the External Secrets Operator to reference external secret stores:

```yaml
# secret-openstack.yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: openstack-secrets
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: vault-backend
    kind: SecretStore
  target:
    name: openstack-keystone-admin
    creationPolicy: Owner
  data:
    - secretKey: OS_PASSWORD
      remoteRef:
        key: understack/keystone
        property: password
```

### Option 2: Sealed Secrets

Use Bitnami Sealed Secrets to commit encrypted secrets:

```bash
# Create a sealed secret
kubeseal --format yaml < secret.yaml > sealed-secret.yaml

# Commit to your deploy repo
git add sealed-secret.yaml
git commit -m "Add sealed secret"
git push
```

### Option 3: SOPS with Age

Use Mozilla SOPS with Age encryption:

```bash
# Install age
brew install age

# Generate key
age-keygen -o age.key

# Encrypt secrets
sops -e --age-age1ABC123... secrets.yaml > secrets.encrypted.yaml

# Add to deploy repo
```

## Complete Example

### Deploy Repository: `https://github.com/myorg/understack-deploy`

```
understack-deploy/
└── sites/
    └── uc-iad3-prod/
        ├── apps.yaml
        ├── dex/
        │   └── values.yaml
        ├── monitoring/
        │   └── values.yaml
        ├── cluster-issuer/
        │   └── letsencrypt.yaml
        └── secret-openstack.yaml
```

**apps.yaml content:**
```yaml
components:
  octavia:
    enabled: false
```

**dex/values.yaml content:**
```yaml
config:
  issuer: https://dex.example.com
  staticClients:
    - id: nautobot
      redirectURIs:
        - https://nautobot.example.com/oauth2/callback
      name: Nautobot
      secret: $DEX_CLIENT_SECRET
```

**monitoring/values.yaml content:**
```yaml
prometheus:
  retention: 30d
  prometheusSpec:
    resources:
      limits:
        memory: 4Gi
    ruleSelector:
      matchLabels:
        prometheus: understack
```

### Deployment Command

```bash
helm install uc-iad3-prod understack/fluxcd \
  --namespace flux-system \
  --create-namespace \
  --set cluster_server=https://kubernetes.default.svc \
  --set understack_url=https://github.com/rackerlabs/understack.git \
  --set understack_ref=main \
  --set deploy_url=https://github.com/myorg/understack-deploy.git \
  --set deploy_ref=main \
  --set deploy_path_prefix=sites
```

## Troubleshooting

### Values Not Applied

1. Check that the path matches: `{{ deploy_path_prefix }}/{{ release_name }}/{{ component }}/values.yaml`
2. Verify the deploy repo is accessible: `flux get sources git`
3. Check HelmRelease status: `flux get helmreleases`

### Path Not Found

If you see errors about missing paths, ensure:
1. The directory exists in your deploy repo
2. The `deploy_path_prefix` is set correctly
3. The release name matches the folder name

### Debug Values Loading

```bash
# View what values are being used
flux get helmrelease <name> -n <namespace>

# Describe for more details
kubectl describe helmrelease <name> -n <namespace>
```
