# Automate Nautobot tokens Provisioning

This document explains the design, flow, and deployment details of the automated Nautobot tokens provisioning system implemented in the UnderStack project.

The feature enables seamless creation and synchronization of Nautobot service accounts and tokens across multiple site clusters using Secret Management Backend ex:(Vault, AKV, PasswordSafe), Kubernetes, Argo Events, and Ansible.

---

## Overview

The automation ensures that whenever service account credentials are created or updated in Secret Management Backend, corresponding Nautobot users and tokens are automatically provisioned.
The workflow is fully event-driven, eliminating manual intervention for user and token management.

**High-level Flow:**

1. Service account details are stored in **Secret Management Backend**.
   Below is the format we expect the credentials to be stored

      ```json
       {
         "credential": {
           "username": "my-nautobot-creds",
           "password": "{\"password\": \"abcxyz\", \"token\": \"rvwe3457797fd4321a79a5f06830701b8xyz12\"}"
         }
       }
    ```

2. Configure **External Secret Store** in the respective namespace.
3. Create **External Secret** in the respective namespace.

    ```yaml
        ---
        apiVersion: external-secrets.io/v1
        kind: ExternalSecret
        metadata:
          name: nautobot-token
          annotations:
            link.argocd.argoproj.io/external-link: https://vault-secret-management-backend.example.com/credentials/12345
        spec:
          refreshInterval: 1h
          secretStoreRef:
            kind: SecretStore
            name: mySecretManagementBackend
          target:
            name: nautobot-token
            creationPolicy: Owner
            template:
              metadata:
                labels:
                  token/type: nautobot
              engineVersion: v2
              type: Opaque
              data:
                hostname: "&#123;&#123; .hostname &#125;&#125;"
                username: "&#123;&#123; .username &#125;&#125;"
                password: "&#123;&#123; index (.password | fromJson) \"password\" &#125;&#125;"
                token: "&#123;&#123; index (.password | fromJson) \"token\" &#125;&#125;"
          dataFrom:
            - extract:
                key: "12345"

    ```

4. A **Kubernetes Secret** is generated in the respective namespace.
5. We packaged as [helm chart](https://github.com/rackerlabs/understack/blob/main/workflows/nautobot-token) which contains EventBus, EventSource and Sensor.
6. Add the [namespace](https://github.com/rackerlabs/understack/blob/main/workflows/kustomization.yaml) in which you want to create nautobot-token.
7. **Argo Events** detects the secret creation or update based on the `token/type=nautobot` label.
8. An [**Ansible job**](https://github.com/rackerlabs/understack/blob/main/ansible/playbooks/nautobot-user-token.yaml) runs automatically to create the corresponding user and token in Nautobot.

---

## Architecture Diagram (Conceptual)

```text
Secret Management Backend ──▶ K8s Secret (nautobot ns)
          │
          ▼
    Argo Event Trigger
          │
          ▼
  Ansible Playbook ──▶ Nautobot API
          │
          ▼
   User + Token Created
```

---

## Key Components

| Component                     | Purpose                                                                     |
|-------------------------------|-----------------------------------------------------------------------------|
| **Secret Management Backend** | Stores service account credentials (username, password and token) securely. |
| **SecretStore**               | Configuration of Secret Management Backend.                                 |
| **Kubernetes Secret**         | Auto-generated representation of credentials.                               |
| **Argo Events**               | Detects changes in secrets and triggers an automated workflow.              |
| **Ansible Playbook**          | Interacts with the Nautobot API to create users and tokens.                 |
| **Nautobot API**              | Endpoint for managing users and tokens programmatically.                    |

---

## Required Secrets

| Secret Name                | Source         | Namespace | Description                                  |
|----------------------------|----------------|-----------|----------------------------------------------|
| `nautobot-superuser-token` | global cluster | nautobot  | Used to bootstrap all other nautobot tokens. |

---

## Usage Flow Summary

1. Add or update service account credentials in **Secret Management Backend**.
2. ExternalSecret sync with Secret Management Backend based on configured interval and generates/updates a **Kubernetes Secret** in respective namespace. ExternalSecret will be in SyncError state if details are not present in **Secret Management Backend**.
3. **Argo Events** detects the change and triggers a workflow.
4. Workflow launches **Ansible Playbook** Job in `nautobot` namespace to interact with Nautobot API.
5. Nautobot user and token are created or updated accordingly.
6. Site clusters continue to use local tokens for operations.

---

## Deployment via Argo CD

The Nautobot service account automation is deployed and managed through **Argo CD** using the following application manifests:

| Manifest                                                                                                          | Description                                                                                                                                  |
|-------------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------|
| [`apps/global/nautobot.yaml`](https://github.com/rackerlabs/understack/blob/main/apps/global/nautobot.yaml)       | Defines the global Nautobot deployment. This configuration is responsible for creating the superuser token and bootstrapping global secrets. |
| [`apps/site/nautobot-site.yaml`](https://github.com/rackerlabs/understack/blob/main/apps/site/nautobot-site.yaml) | Reference to deploy directory containing Site cluster nautobot secrets                                                                       |

### Deployment Workflow

1. **Global Nautobot Deployment**
    - The global Argo CD application (`nautobot.yaml`) deploys the base Nautobot configuration and generates a **superuser token**.
    - This token is stored securely as a Kubernetes Secret in the `nautobot` namespace of the global cluster.
    - Another responsibility of global cluster is to create superuser token of site clusters which is used by site cluster to bootstrap other tokens.
      - example: global cluster (staging) creates site cluster super-user (rxdb-lab) secret and creates user and token in nautobot.
    - In deploy repo create sites cluster superuser secrets in `"&#123;&#123;.name&#125;&#125;/manifests/nautobot-site` directory as defined in [`apps/site/nautobot-site.yaml`](https://github.com/rackerlabs/understack/blob/main/apps/site/nautobot-site.yaml).

2. **Site Nautobot Deployment**
    - Each site’s Argo CD application (`nautobot-site.yaml`) only creates secrets.
    - Site cluster creates secret of **superuser** (do not add `token/type=nautobot` label).
    - The site retrieves the **superuser token** and uses it to authenticate against Nautobot.
    - Site-specific **service accounts and tokens** are then created through Argo Events and Ansible workflows.
    - Global cluster's superuser token is not used anywhere in site cluster.
    - In deploy repo define superuser bootstrap secret in `"&#123;&#123;.name&#125;&#125;/manifests/nautobot-site` directory as defined in [`apps/site/nautobot-site.yaml`](https://github.com/rackerlabs/understack/blob/main/apps/site/nautobot-site.yaml).

3. **Automation Integration**
    - When new site credentials are created in Secret Management Backend, the change triggers the site-level automation flow.
    - The site Nautobot instance creates or updates its user and token accordingly.

---

## Nautobot Secrets in Global Cluster

| nautobot Secret Name      | Namespace     | label                | token user in Nautobot  | Description                                                        |
|---------------------------|---------------|----------------------|-------------------------|--------------------------------------------------------------------|
| `nautobot-superuser`      | `nautobot`    |                      | admin                   | Currently it is a SealedSecret, Token used to access Nautobot API. |
| `nautobot-token`          | `openstack`   | token/type: nautobot | cluster-name-openstack  | Token used by openstack services to access Nautobot.               |
| `nautobot-token`          | `argo-events` | token/type: nautobot | cluster-name-workflow   | Token used by workflow jobs to access Nautobot.                    |
| `site-cluster-name-token` | `nautobot`    | token/type: nautobot | site-cluster-name-token | Token used by Site cluster to bootstrap other tokens.              |

---

## Nautobot Secrets in Site Cluster

| nautobot Secret Name | Namespace     | label                | token user in Nautobot | Description                                          |
|----------------------|---------------|----------------------|------------------------|------------------------------------------------------|
| `nautobot-superuser` | `nautobot`    |                      | cluster-name-openstack | Token used to access Nautobot API.                   |
| `nautobot-token`     | `openstack`   | token/type: nautobot | cluster-name-openstack | Token used by openstack services to access Nautobot. |
| `nautobot-token`     | `argo-events` | token/type: nautobot | cluster-name-workflow  | Token used by workflow jobs to access Nautobot.      |

---

## References

- **PR:** [rackerlabs/understack#1318](https://github.com/rackerlabs/understack/pull/1318)

---
