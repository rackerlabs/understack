# External Secrets Guide

This guide explains how to automate Kubernetes secrets creation using
external secret stores (Vault, AWS Secrets Manager, etc.) and ArgoCD
components in the UnderStack environment.

------------------------------------------------------------------------

## TL;DR Quick Steps

1. **Assumption**: Credentials already exist in an external system
   (Vault, AWS Secrets Manager, PasswordSafe, etc.).
2. **Install SecretStore** in the desired Kubernetes namespace.
3. **Create ArgoCD component** in [apps/site/](https://github.com/rackerlabs/understack/tree/main/apps/site)
   to manage SecretStore + ExternalSecrets.
4. **Configure `values.yaml`** to define secret templates.
5. **Apply ArgoCD application** to deploy SecretStore and
   ExternalSecrets.

------------------------------------------------------------------------

## Assumptions

- Credentials are managed in external systems (Vault, AWS Secrets
  Manager, PasswordSafe).
- Secrets must be pulled automatically into Kubernetes clusters.

------------------------------------------------------------------------

## Workflow

1. **Create an External SecretStore per Kubernetes namespace**.
   This links Kubernetes to the external backend (Vault, AWS Secrets
   Manager, etc.).

2. **Create an ArgoCD component** inside the site repo:
   Example:
   [nautobot-secretstore-gen-secrets.yaml](https://raw.githubusercontent.com/rackerlabs/understack/refs/heads/main/apps/site/nautobot-secretstore-gen-secrets.yaml)

   This ArgoCD component performs two tasks:

    - Installs the SecretStore.
    - Creates ExternalSecrets referencing the SecretStore.

3. **Deploy via Kustomize/Helm**

    - One Helm chart installs the SecretStore pointing to the external
      backend system.
    - Another Helm chart creates the ExternalSecrets from that
      SecretStore.

4. **Configure `values.yaml`** with templates for secrets.

------------------------------------------------------------------------

## Example ArgoCD Component

``` yaml
---
component: nautobot-secrets
componentNamespace: nautobot
sources:
  - ref: understack
    path: 'components/secretstore-gen-secrets'
    helm:
      releaseName: nautobot-secrets
      valueFiles:
        - $deploy/&#123;&#123;.name&#125;&#125;/helm-configs/secretstore-nautobot-secrets.yaml
      ignoreMissingValueFiles: true
  - ref: deploy
    path: '&#123;&#123;.name&#125;&#125;/manifests/secret-store'
```

------------------------------------------------------------------------

## Sample values.yaml

``` yaml
# yaml-language-server: $schema=https://rackerlabs.understack.io/schema/component-secretstore-gen-secrets.schema.json
---
secretStore:
  kind: SecretStore
  name: pwsafe

secrets:
  - name: site1-token
    externalLinkAnnotationTemplate: "https://secretvault.example.com/credentials/373525"
    templateData:
      hostname: "&#123;&#123; .hostname &#125;&#125;"
      username: "&#123;&#123; .username &#125;&#125;"
      password: "&#123;&#123; .password &#125;&#125;"
      token: "&#123;&#123; .token &#125;&#125;"
    dataFrom:
      - extract:
          key: "373525"

  - name: site2-token
    externalLinkAnnotationTemplate: "https://secretvault.example.com/credentials/373539"
    labels:
      token/type: mycustomlabel
    templateData:
      hostname: "&#123;&#123; .hostname &#125;&#125;"
      username: "&#123;&#123; .username &#125;&#125;"
      password: "&#123;&#123; .password &#125;&#125;"
      token: "&#123;&#123; .token &#125;&#125;"
    dataFrom:
      - extract:
          key: "373539"
```

------------------------------------------------------------------------

## Summary

- **External systems** (Vault, AWS Secrets Manager, PasswordSafe) hold
  credentials.
- **SecretStore** bridges Kubernetes to the external backend.
- **ExternalSecrets** define the actual K8s secrets created from
  external data.
- **ArgoCD components** ensure consistent automation of this workflow
  across namespaces.
