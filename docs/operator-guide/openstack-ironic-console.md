# Ironic Graphical Console guide

This guide explains how the Graphical Console feature is implemented for
baremetal nodes.

## Overview

The overall goal of this is to provide the Undercloud users
with an out-of-band, graphical console access to their provisioned nodes. At
the same time, we do not want to give them full access to DRAC / iLo
interfaces, nor do we want to share the access credentials.

Graphical console access feature is realised using several different components
stitched together.

You can see how they all fit together on a diagram in [components](#components) section.
Here is brief explanation of what each component is responsible for:

- **User** is typically interacting with Ironic **API** through the Openstack
  **CLI** and uses web **browser** to access the console
- Ironic **Conductor** is responsible for starting the **console containers**
  upon user request
- Ironic **Conductor** is also responsible for creating a Kubernetes secret
  with the credentials to access the console
- **Console VNC Containers** are like a mini jump host desktops that can run
  only one application - a browser with a HTML5 console exposed by the
  baremetal nodes BMC. These containers are accessible (internally) through
  VNC.
- **ironic-novncproxy** is launched alongside the **Ironic Conductor** and as
  the name implies, it proxies users HTTPS traffic. It does that by serving
  [noVNC](https://github.com/novnc/noVNC) web application to the user's
  browser. The browser then opens websocket connection to the
  **ironic-novncproxy** which in turn opens VNC connection to the relevant
  **container**.

## Sequence diagram

Below diagram shows the sequence of events that occur during typical session
when the user or operator opens the console.

```mermaid
sequenceDiagram
    participant User
    participant CLI
    participant Browser
    participant IronicAPI
    participant Conductor
    participant NoVNCProxy
    participant Container
    participant BMC

    User->>CLI: baremetal node console enable
    CLI->>IronicAPI: REST API call to enable console
    IronicAPI->>Conductor: Enable console
    Conductor->>Conductor: Create & store time-limited token
    Conductor->>Conductor: Start container (virtual X11, browser, VNC server)

    User->>CLI: baremetal node console show
    CLI->>IronicAPI: REST API call to fetch console URL
    IronicAPI-->>User: Returns console URL
    User->>Browser: open console page
    Browser->>NoVNCProxy: Access console URL
    NoVNCProxy->>Browser: Serve NoVNC web assets

    Browser->>NoVNCProxy: Initiate WebSocket
    NoVNCProxy->>NoVNCProxy: Lookup node & validate token

    NoVNCProxy->>Container: VNC connection
    Container->>BMC: Connect to DRAC/iLO endpoint
    BMC->Container: ""
    Container->>NoVNCProxy: ""
    NoVNCProxy->>Browser: HTML5 console
```

## Components

A typical deployment will have several components running to provide console functionality.

Please note:

- Each baremetal node console session gets it's own VNC container
- There is a 1:1 coupling between the Ironic conductor and the Ironic NOVNCProxy

```mermaid
flowchart LR

%% --- Nodes / groups ---
subgraph Access
direction TB
U[User]
B[browser]
C[CLI]
GW[API gateway]
end


subgraph Core
direction TB
IA[ironic-api]
N0[ironic-novncproxy-0]
N1[ironic-novncproxy-1]
end



subgraph Conductors
direction TB
C0[ironic-conductor-0]
C1[ironic-conductor-1]
end

subgraph Consoles
direction TB
V0a[console-vnc-0a]
V0b[console-vnc-0b]
V0c[console-vnc-0c]
V0d[console-vnc-0d]
V1a[console-vnc-1a]
V1b[console-vnc-1b]
end

subgraph Servers
direction TB
S0a[srv-0a]
S0b[srv-0b]
S0c[srv-0c]
S0d[srv-0d]
S1a[srv-1a]
S1b[srv-1b]
end

%% -------------------------------------------------------------------
%% IMPORTANT: protocol links are defined FIRST so linkStyle indices match
%% -------------------------------------------------------------------

%% Console containers -> servers (HTTPS) [links 0..5]
V0a -- https --> S0a
V0b --> S0b
V0c --> S0c
V0d --> S0d
V1a --> S1a
V1b --> S1b



%% Conductors -> servers (Redfish) [links 6..11]
C0 --> S0a
C0 --> S0b
C0 --> S0c
C0 --> S0d
C1 --> S1a
C1 -- redfish --> S1b

%% Style HTTPS links (thick + green)
linkStyle 0 stroke-width:4px,stroke:#2e7d32
linkStyle 1 stroke-width:4px,stroke:#2e7d32
linkStyle 2 stroke-width:4px,stroke:#2e7d32
linkStyle 3 stroke-width:4px,stroke:#2e7d32
linkStyle 4 stroke-width:4px,stroke:#2e7d32
linkStyle 5 stroke-width:4px,stroke:#2e7d32

%% Style Redfish links (dashed + blue)
linkStyle 6 stroke-dasharray: 6 4,stroke:#1565c0
linkStyle 7 stroke-dasharray: 6 4,stroke:#1565c0
linkStyle 8 stroke-dasharray: 6 4,stroke:#1565c0
linkStyle 9 stroke-dasharray: 6 4,stroke:#1565c0
linkStyle 10 stroke-dasharray: 6 4,stroke:#1565c0
linkStyle 11 stroke-dasharray: 6 4,stroke:#1565c0

%% --- Everything else (unstyled) ---
U --> C
U --> B
B --> GW
C --> GW

GW -- http --> IA
GW -- https --> N0
GW -- "http(s)? + websocket" --> N1

IA --> C0
IA --> C1

N0 -- vnc --> V0a
N0 -- vnc --> V0b
N0 -- vnc --> V0c
N0 -- vnc --> V0d

N1 -- vnc --> V1a
N1 -- vnc --> V1b
```

## Environment requirements and configuration

Following per-environment configurations must be made to enable graphical
console feature:

1. The baremetal nodes' console_interface must be set to a graphical driver
   such as `redfish-graphical`.
2. Ironic must have the relevant drivers enabled in `enabled_console_interfaces`
3. `ironic-novncproxy` must be launched for each of the ironic conductors. At
   the time of writing, this is achieved through `extraContainers` because
   OpenStack Helm does not have direct support for launching that component. We
   plan to contribute that feature to [OSH][3] soon.
4. Each instance of the `ironic-novncproxy` must be exposed to the external
   world. This means, we have to create relevant Kubernetes `Service` and
   `HTTPRoute` definitions. The `cert-manager` will take care of TLS certificates
   and `external-dns` will register the DNS domain.
5. *(Optional)* The RBAC policy may need to be adjusted as the baremetal console,
   by default is only accessible to admins.

## Docs

- [ironic VNC config][1] documentation
- [ironic - Graphical Console support][2]

[1]: https://docs.openstack.org/ironic/latest/configuration/config.html#vnc
[2]: https://docs.openstack.org/ironic/latest/install/graphical-console.html
[3]: https://github.com/RSS-Engineering/undercloud-deploy/commit/d7201742ae5e10b9428be17b7418ac1066899214
