# FluxCD Deploy Repo Example

This is an example of how to structure a deploy repository for use with the FluxCD-based UnderStack deployment.

## Overview

Unlike ArgoCD's multi-source feature, FluxCD's HelmRelease doesn't directly support multiple Git sources for values. Instead, the deploy repo uses **Kustomization patches** to:

1. Override Helm chart values
2. Add Secrets
3. Add ConfigMaps

## Structure

```
flux-deploy-repo/
├── README.md
├── deploy.yaml              # Environment configuration (optional)
├── kustomization.yaml       # Root kustomization
├── cert-manager/
│   ├── kustomization.yaml  # Patches the HelmRelease
│   └── cluster-issuer.yaml # Optional: additional CRs
├── monitoring/
│   └── kustomization.yaml
├── nautobot/
│   ├── kustomization.yaml
│   └── secrets.yaml       # Secrets (ExternalSecret or SealedSecret)
├── keystone/
│   └── ...
└── rook/
    └── ...
```

Each component folder contains a `kustomization.yaml` that:
- Patches the HelmRelease to add values
- References secrets or additional resources

## How It Works

### 1. The HelmRelease (in understack repo)

The understack repo creates a HelmRelease like:

```yaml
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: understack-flux-monitoring
  namespace: monitoring
spec:
  chart:
    spec:
      chart: kube-prometheus-stack
      sourceRef:
        kind: HelmRepository
        name: prometheus-community
```

### 2. The Kustomization (in deploy repo)

The deploy repo creates a Kustomization that patches the HelmRelease directly:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: monitoring
patches:
  - target:
      kind: HelmRelease
      name: understack-flux-monitoring
    patch: |
      - op: add
        path: /spec/values
        value:
          grafana:
            ingress:
              enabled: true
              hostname: grafana.example.com
```

Note: The values are defined inline in the patch. You can keep a separate `values.yaml` file for reference/documentation if desired, but it won't be automatically applied unless referenced by a patch.

## Environment Organization

You can organize your deploy repo by environment:

- `global/` - Values common to all environments
- `site/dev/` - Development environment overrides
- `site/prod/` - Production environment overrides

Set the `deploy_path_prefix` in your values to point to the appropriate folder.

## Secrets

Secrets should be stored as:

1. **ExternalSecrets** - For integration with external secret stores (Vault, AWS Secrets Manager, etc.)
2. **SealedSecrets** - For GitOps-friendly encrypted secrets
3. **plain Secrets** - For development/testing only

Example with ExternalSecret:

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: nautobot-secrets
  namespace: nautobot
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: vault-store
    kind: SecretStore
  target:
    name: nautobot-secret
  data:
    - secretKey: NAUTOBOT_SECRET_KEY
      remoteRef:
        key: nautobot/secret-key
```

## Usage with the Helm Chart

In your values file for the understack fluxcd chart:

```yaml
deploy_url: https://github.com/your-org/deploy-repo.git
deploy_path_prefix: site/dev
deploy_ref: main
```

This tells FluxCD to:
1. Create a GitRepository pointing to your deploy repo
2. Look for Kustomizations in `site/dev/` folder
3. Use the `main` branch
