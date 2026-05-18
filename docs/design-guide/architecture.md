# Architecture Overview

UnderStack is split across two cluster types: a **global cluster** hosting shared
services, and one or more **site clusters** hosting the OpenStack compute plane.

## Service Layout

```mermaid
graph TB
    IDP["External Identity Provider<br/>(e.g. Azure Entra / LDAP)"]:::external

    subgraph global["Global Cluster"]
        Dex["Dex<br/>(OIDC Broker)"]:::otheross
        Nautobot["Nautobot<br/>(Network Source of Truth)"]:::otheross
        Keystone["Keystone<br/>(Identity Service)"]:::openstack
    end

    subgraph site["Site Cluster(s)"]
        Ironic["Ironic<br/>(Bare Metal)"]:::openstack
        Placement["Placement"]:::openstack
        Neutron["Neutron<br/>(Networking)"]:::openstack
        Glance["Glance<br/>(Images)"]:::openstack
        Nova["Nova<br/>(Compute)"]:::openstack
        Cinder["Cinder<br/>(Block Storage)"]:::openstack
    end

    subgraph legend["Key"]
        OS_KEY["OpenStack Service"]:::openstack
        OSS_KEY["Other Open Source"]:::otheross
        EXT_KEY["External System"]:::external
    end

    IDP -->|"authenticates users"| Dex
    Dex -->|"OIDC"| Nautobot
    Dex -->|"OIDC"| Keystone

    Keystone -->|"auth token validation"| Ironic
    Keystone -->|"auth token validation"| Placement
    Keystone -->|"auth token validation"| Neutron
    Keystone -->|"auth token validation"| Glance
    Keystone -->|"auth token validation"| Nova
    Keystone -->|"auth token validation"| Cinder

    classDef openstack fill:#fed7aa,stroke:#ea580c,color:#000
    classDef otheross fill:#bfdbfe,stroke:#3b82f6,color:#000
    classDef external fill:#e2e8f0,stroke:#64748b,color:#000
```

## Authentication Flow

All user authentication is brokered through **Dex**, which acts as an OIDC
federation layer in front of your external Identity Provider (IdP). This means
you only need to configure your IdP connection once in Dex, and all services
inherit that integration.

- **Nautobot** uses Dex for SSO, allowing operators to log in with their
  corporate credentials.
- **Keystone** is configured with Dex as its OIDC provider, so all OpenStack
  API access and dashboard logins flow through Dex to the external IdP.

Once a user is authenticated via Keystone, the resulting token is trusted by
all site cluster OpenStack services (Ironic, Placement, Neutron, Glance, Nova,
Cinder). Those services validate tokens against Keystone but do not interact
with Dex or the external IdP directly.
