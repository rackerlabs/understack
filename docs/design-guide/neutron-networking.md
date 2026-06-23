# Neutron Networking

The focus of UnderStack is on on delivering bare metal systems while wanting
to provide a cloud like experience there are a number of SDN functions that
must be implemented. By utilizing OpenStack Neutron as the user facing API
many of these features can be achieved.

To enable this we are using the following plugins/features of Neutron:

- [OVN driver][ovn-driver] for general [OVN][ovn] support — loaded first so it
  creates virtual ports for routers before the baremetal drivers run, as
  recommended by [networking-baremetal][networking-baremetal]
- [networking-baremetal][networking-baremetal] to have Neutron aware of the physical
  networks of Ironic baremetal ports.
- our custom mechanism drivers `understack` and `undersync` (both must be loaded,
  with `baremetal` from [networking-baremetal][networking-baremetal] loaded between them)
- [ovn-router][ovn-admin] as the L3 router plugin
- [trunk plugin][neutron-trunk] service plugin
- [network segment range][neutron-network-segment-range] service plugin

The physical network design for each site is a leaf/spine configuration
so to best support this we use the VXLAN type driver with VLANs on all the
leaves bound to the VXLAN VNI. In this configuration there is only one subnet
across the network, in Neutron this is called [L2 Adjacency][neutron-l2-adjacency].
This model has been used by networking vendors such as Arista, Juniper, and Cisco
in their own ML2 mechanism driver. However full support for this has been lacking
upstream so we have developed our own mechanism driver as we explore the best
approach. Traditionally Ironic (baremetal) based Neutron deployment have utilized
the [networking-generic-switch][networking-generic-switch] mechanism however as it
stands today it only supports VLAN and it's templating capabilities are not sufficient
for our needs. We hope to eventually create a generic mechanism which can be contributed
back. Another limitation that we are aware of is in the VXLAN type driver itself,
the Neutron team designed this type as an overlay style VXLAN system while we are
focused on an underlay or EVPN-VXLAN style system. We are actively working with
upstream on how to best include this use case.

## Mapping Leaf/Spine to Neutron Networks

In a Leaf/Spine fabric, VXLAN VNIs are used to create virtual network segments
that run over the IP underlay. On the leaf switches, traditional VLANs connected
to physical assets are typically mapped to specific VNIs to provide connectivity
across the fabric.

### VNIs

An available pool of VNIs is defined by creating a VXLAN [network segment range][neutron-network-segment-range]
with the same name as the fabric on which the VNIs will reside.

<!-- markdownlint-capture -->
<!-- markdownlint-disable MD046 -->
!!! Note

    This is one of the places that the underlay vs overlay VXLAN disconnect
    rears its head. Neutron assumes that all VXLAN participants will be able
    to reach each other via the tunnel configuration. However it is possible
    to have multiple physically separate fabrics but Neutron does not allow
    the VXLAN type to have a `physical_network` value like VLAN networks.
<!-- markdownlint-restore -->

Provider networks and self-serviced tenant networks are allocated VNIs from this range.

### VLANs

For each leaf pair on the fabric a VLAN [network segment range][neutron-network-segment-range]
is created with the `physical_network` value set to their pair name. For example,
the name of the rack they serve could be used.

### Connecting a Server to a Network

When a server needs to establish a connection to a network, Ironic takes all
the baremetal ports assigned to that server and compares each
baremetal port's `local_link_connection` and `physical_network` attributes to
the desired network to determine the correct port to use.
This process is documented is documented in Ironic's
Networking Guide as [VIF Attachment][ironic-vif-attachment]. Changes to this
process are coming in a forthcoming Ironic spec for [dynamic port attachment][ironic-spec-dpa].

If the VNI that is associated with the VXLAN network is not already mapped to
a VLAN on the leaf pair where the server is being connected
then there will not be a `physical_network` match to a segment in the network and
one of the baremetal port's of the server. In this case
we will not have a VLAN segment, so we will allocate a new VLAN
in the correct leaf pair by utilizing the `physical_network` of one of the
baremetal ports to create a VLAN segment and attach it to the VXLAN network. The
mechanism is then responsible for then ensuring the switch configuration is applied.
The code then re-attempts this operation and this time finds a match and is able to
use it.

For more technical details on this operation see the Bind Port section.

### Routing Network Traffic

Networks by default are isolated from each other and do not support any data ingress
or egress by default. To route traffic between networks and to provide ingress and
egress, Neutron provides router support. Neutron router support is implemented by a
plugin. In the case of UnderStack, since OVN is being utilized the [OVN L3 plugin][ovn-routers]
is used. This plugin provides for the ability to define different
[router flavors][ovn-router-flavors] so that more than just OVN can be used to route
traffic. Router flavor plugins can be crafted to encompass physical devices or
virtual devices upon which other features can be provided.

Routers operate the same as baremetal servers. A VLAN must exist on the leaf pair
where the virtual or physical router is being served from so that traffic can be
handled.

## A View from the Neutron API/CLI

First we'll create a self-serviced tenant network with the following:

```bash
openstack network create milantest
# Fictional output because this network was already created and also
# had a subnet created for it. We've also got additional permissions
# to view the provider information to help with the explanation.
+---------------------------+--------------------------------------+
| Field                     | Value                                |
+---------------------------+--------------------------------------+
| admin_state_up            | UP                                   |
| availability_zone_hints   |                                      |
| availability_zones        |                                      |
| created_at                | 2025-02-12T18:32:40Z                 |
| description               |                                      |
| dns_domain                | None                                 |
| id                        | 783b4239-7220-4a74-8253-415539469860 |
| ipv4_address_scope        | None                                 |
| ipv6_address_scope        | None                                 |
| is_default                | None                                 |
| is_vlan_qinq              | None                                 |
| is_vlan_transparent       | None                                 |
| l2_adjacency              | True                                 |
| mtu                       | 9000                                 |
| name                      | milantest                            |
| port_security_enabled     | False                                |
| project_id                | d3c2c86bdbf24ff5843f323524b63768     |
| provider:network_type     | vxlan                                |
| provider:physical_network | None                                 |
| provider:segmentation_id  | 200004                               |
| qos_policy_id             | None                                 |
| revision_number           | 2                                    |
| router:external           | Internal                             |
| segments                  | None                                 |
| shared                    | False                                |
| status                    | ACTIVE                               |
| subnets                   | 6f8e3a32-c7a7-4354-808f-75800b21efcf |
| tags                      |                                      |
| updated_at                | 2025-04-25T12:40:34Z                 |
+---------------------------+--------------------------------------+
```

From the northbound side of OVN we see the following about this network:

```bash
ovn-nbctl show
# snip extra output
switch 9077901b-2a7b-46ed-a012-59bcce9a4da3 (neutron-783b4239-7220-4a74-8253-415539469860) (aka milantest)
# snip extra output
```

You will see that a virtual switch is created with the same name and its ID matches the network ID.

### Attaching servers to networks

Now there's a network that can be used to attach a server to. We'll go
ahead and assume a server was built and attached to the network.

We can see how this server got connected to the network by looking at the segments.

```bash
openstack network segment list --network milantest
+--------------------------------------+------------------+--------------------------------------+--------------+---------+
| ID                                   | Name             | Network                              | Network Type | Segment |
+--------------------------------------+------------------+--------------------------------------+--------------+---------+
| 5ab3339d-ae44-4f45-9293-7b41a83bf473 | None             | 783b4239-7220-4a74-8253-415539469860 | vlan         |    1800 |
| 78be9792-cf21-4c5e-8432-bd83f0830763 | None             | 783b4239-7220-4a74-8253-415539469860 | vxlan        |  200004 |
+--------------------------------------+------------------+--------------------------------------+--------------+---------+

openstack network segment show 5ab3339d-ae44-4f45-9293-7b41a83bf473
+------------------+--------------------------------------+
| Field            | Value                                |
+------------------+--------------------------------------+
| created_at       | 2025-04-29T13:21:31Z                 |
| description      | None                                 |
| id               | 5ab3339d-ae44-4f45-9293-7b41a83bf473 |
| name             | None                                 |
| network_id       | 783b4239-7220-4a74-8253-415539469860 |
| network_type     | vlan                                 |
| physical_network | f20-2-network                        |
| revision_number  | 0                                    |
| segmentation_id  | 1800                                 |
| updated_at       | 2025-04-29T13:21:31Z                 |
+------------------+--------------------------------------+
```

Now we can check the ports to confirm that this segment exists to provide
connectivity to this server.

```bash
openstack port list --network milantest
+--------------------------------------+-----------------+-------------------+--------------------------------------------------------------------------------+--------+
| ID                                   | Name            | MAC Address       | Fixed IP Addresses                                                             | Status |
+--------------------------------------+-----------------+-------------------+--------------------------------------------------------------------------------+--------+
| 47bb4c37-f60d-474f-8ce5-c7c1d9982585 | trunk_parent11  | 14:23:f3:f5:22:b0 | ip_address='192.168.100.170', subnet_id='6f8e3a32-c7a7-4354-808f-75800b21efcf' | ACTIVE |
+--------------------------------------+-----------------+-------------------+--------------------------------------------------------------------------------+--------+

openstack baremetal port list --address '14:23:f3:f5:22:b0' --fields physical_network internal_info
+------------------+----------------------------------------------------------------+
| Physical Network | Internal Info                                                  |
+------------------+----------------------------------------------------------------+
| f20-2-network    | {'tenant_vif_port_id': '47bb4c37-f60d-474f-8ce5-c7c1d9982585'} |
+------------------+----------------------------------------------------------------+
```

You will see in the last output that the `tenant_vif_port_id` matches the ID of the Neutron
port when we shows the ports on the network.

This process will be repeated for every server that is connected to the network. If a
server is connected to a leaf with an existing segment then an additional VLAN will not
be consumed.

Similarly on the northbound of OVN we will see the port appear on the virtual switch.

```bash
ovn-nbctl show
# snip extra output
switch 9077901b-2a7b-46ed-a012-59bcce9a4da3 (neutron-783b4239-7220-4a74-8253-415539469860) (aka milantest)
    port 47bb4c37-f60d-474f-8ce5-c7c1d9982585 (aka trunk_parent11)
        type: external
        addresses: ["14:23:f3:f5:22:b0 192.168.100.170"]
# snip extra output
```

Once again the naming and the IDs match up with the port as it exists in Neutron to aid debugging.

### Attaching routers to networks

Attaching a router to a network operates similarly to attaching servers except that
the router port will be trunked to our Neutron Network node.

Firstly we'll create a router.

```bash
openstack router create puc-908
+---------------------------+--------------------------------------+
| Field                     | Value                                |
+---------------------------+--------------------------------------+
| admin_state_up            | UP                                   |
| availability_zone_hints   |                                      |
| availability_zones        |                                      |
| created_at                | 2025-05-01T15:13:06Z                 |
| description               |                                      |
| enable_default_route_bfd  | False                                |
| enable_default_route_ecmp | False                                |
| enable_ndp_proxy          | None                                 |
| external_gateway_info     | null                                 |
| external_gateways         | []                                   |
| flavor_id                 | None                                 |
| ha                        | False                                |
| id                        | 85533c29-d1f1-42f8-a133-d15099318f3a |
| interfaces_info           | []                                   |
| name                      | puc-908                              |
| project_id                | d3c2c85bdbf24ff5843f323524b63768     |
| revision_number           | 1                                    |
| routes                    |                                      |
| status                    | ACTIVE                               |
| tags                      |                                      |
| tenant_id                 | d3c2c85bdbf24ff5843f323524b63768     |
| updated_at                | 2025-05-01T21:09:19Z                 |
+---------------------------+--------------------------------------+
```

We'll see this object get created in OVN as well.

```bash
ovn-nbctl show
# snip extra output
router 81a34be1-bbb3-4ae4-8d3e-d9b7bf3992b4 (neutron-85533c29-d1f1-42f8-a133-d15099318f3a) (aka puc-908)
# snip extra output
```

The name and the ID continue to match up with data inside of Neutron. Now we can attach our
network's subnet to the router.

```bash
openstack router add subnet puc-908 6f8e3a32-c7a7-4354-808f-75800b21efcf
+---------------------------+-------------------------------------------------------------------------------------------------------------------------------------------+
| Field                     | Value                                                                                                                                     |
+---------------------------+-------------------------------------------------------------------------------------------------------------------------------------------+
| admin_state_up            | UP                                                                                                                                        |
| availability_zone_hints   |                                                                                                                                           |
| availability_zones        |                                                                                                                                           |
| created_at                | 2025-05-01T15:13:06Z                                                                                                                      |
| description               |                                                                                                                                           |
| enable_default_route_bfd  | False                                                                                                                                     |
| enable_default_route_ecmp | False                                                                                                                                     |
| enable_ndp_proxy          | None                                                                                                                                      |
| external_gateway_info     | null                                                                                                                                      |
| external_gateways         | []                                                                                                                                        |
| flavor_id                 | None                                                                                                                                      |
| ha                        | True                                                                                                                                      |
| id                        | 85533c29-d1f1-42f8-a133-d15099318f3a                                                                                                      |
| interfaces_info           | [{"port_id": "10099d3c-0ade-41b9-8a1c-1d50ace4bf22", "ip_address": "192.168.100.1", "subnet_id": "6f8e3a32-c7a7-4354-808f-75800b21efcf"}] |
| name                      | puc-908                                                                                                                                   |
| project_id                | d3c2c85bdbf24ff5843f323524b63768                                                                                                          |
| revision_number           | 4                                                                                                                                         |
| routes                    |                                                                                                                                           |
| status                    | ACTIVE                                                                                                                                    |
| tags                      |                                                                                                                                           |
| tenant_id                 | d3c2c85bdbf24ff5843f323524b63768                                                                                                          |
| updated_at                | 2025-05-01T21:10:39Z                                                                                                                      |
+---------------------------+-------------------------------------------------------------------------------------------------------------------------------------------+
```

We'll look at the segments and how they're attached.

```bash
openstack network segment list --network milantest
+--------------------------------------+------------------+--------------------------------------+--------------+---------+
| ID                                   | Name             | Network                              | Network Type | Segment |
+--------------------------------------+------------------+--------------------------------------+--------------+---------+
| 059fd287-4fd1-446f-a506-e0ed9276f67d | None             | 783b4239-7220-4a74-8253-415539469860 | vlan         |    1801 |
| 5ab3339d-ae44-4f45-9293-7b41a83bf473 | None             | 783b4239-7220-4a74-8253-415539469860 | vlan         |    1800 |
| 78be9792-cf21-4c5e-8432-bd83f0830763 | None             | 783b4239-7220-4a74-8253-415539469860 | vxlan        |  200004 |
+--------------------------------------+------------------+--------------------------------------+--------------+---------+

openstack network segment show 059fd287-4fd1-446f-a506-e0ed9276f67d
+------------------+--------------------------------------+
| Field            | Value                                |
+------------------+--------------------------------------+
| created_at       | 2025-05-01T20:45:16Z                 |
| description      |                                      |
| id               | 059fd287-4fd1-446f-a506-e0ed9276f67d |
| name             | None                                 |
| network_id       | 783b4239-7220-4a74-8253-415539469860 |
| network_type     | vlan                                 |
| physical_network | f20-1-network                        |
| revision_number  | 2                                    |
| segmentation_id  | 1801                                 |
| updated_at       | 2025-05-01T20:55:24Z                 |
+------------------+--------------------------------------+
```

This time we can see a different VLAN is selected on a different leaf. We can confirm this via
our ports.

```bash
openstack port list --network milantest
+--------------------------------------+-----------------+-------------------+--------------------------------------------------------------------------------+--------+
| ID                                   | Name            | MAC Address       | Fixed IP Addresses                                                             | Status |
+--------------------------------------+-----------------+-------------------+--------------------------------------------------------------------------------+--------+
| 10099d3c-0ade-41b9-8a1c-1d50ace4bf22 |                 | fa:16:3e:10:8f:f1 | ip_address='192.168.100.1', subnet_id='6f8e3a32-c7a7-4354-808f-75800b21efcf'   | ACTIVE |
| 47bb4c37-f60d-474f-8ce5-c7c1d9982585 | trunk_parent11  | 14:23:f3:f5:22:b0 | ip_address='192.168.100.170', subnet_id='6f8e3a32-c7a7-4354-808f-75800b21efcf' | ACTIVE |
+--------------------------------------+-----------------+-------------------+--------------------------------------------------------------------------------+--------+
```

Inside of OVN we see the following data:

```bash
ovn-nbctl show
# snip extra output
switch 9077901b-2a7b-46ed-a012-59bcce9a4da3 (neutron-783b4239-7220-4a74-8253-415539469860) (aka milantest)
    port 47bb4c37-f60d-474f-8ce5-c7c1d9982585 (aka trunk_parent11)
        type: external
        addresses: ["14:23:f3:f5:22:b0 192.168.100.170"]
    port 10099d3c-0ade-41b9-8a1c-1d50ace4bf22
        type: router
        router-port: lrp-10099d3c-0ade-41b9-8a1c-1d50ace4bf22
    port provnet-059fd287-4fd1-446f-a506-e0ed9276f67d
        type: localnet
        tag: 1801
        addresses: ["unknown"]
router 81a34be1-bbb3-4ae4-8d3e-d9b7bf3992b4 (neutron-85533c29-d1f1-42f8-a133-d15099318f3a) (aka puc-908)
    port lrp-10099d3c-0ade-41b9-8a1c-1d50ace4bf22
        mac: "fa:16:3e:10:8f:f1"
        networks: ["192.168.100.1/24"]
# snip extra output
```

The names and the IDs all match, along with the VLAN ID of the segment where the node running OVN resides.

## ML2 Mechanism Operations

Our ML2 mechanism is split across two drivers that must both be present in
`mechanism_drivers`, with the `baremetal` driver from
[networking-baremetal][networking-baremetal] loaded between them:

- `understack` — the primary driver responsible for allocating dynamic VLAN
  segments on VXLAN networks (`bind_port()`), releasing them when ports are
  removed (`delete_port_postcommit()`), and triggering switch configuration
  updates (`update_port_postcommit()`)
- `baremetal` — the [networking-baremetal][networking-baremetal] driver that
  makes Neutron aware of the physical networks of Ironic baremetal ports
- `undersync` — handles level-1 binding by calling `set_binding()`
  on the VLAN segment that `understack` allocated via `continue_binding()`;
  without it port binding fails at level 1

The binding flow is: `understack` handles the VXLAN segment at level 0 and
calls `continue_binding()` with a dynamically allocated VLAN segment, then
`undersync` finalises the binding at level 1 by calling
`set_binding()` on that VLAN segment.

Together they are responsible for:

- creating dynamic VLAN segments on VXLAN networks via port binding operations via `bind_port()`
- deleting dynamic VLAN segments on VXLAN networks when ports are removed via `delete_port_postcommit()`
- triggering the actual operation to update the leaf/spine devices to provide the connectivity via `update_port_postcommit()`

```mermaid
sequenceDiagram
    participant Client
    participant NeutronAPI
    participant ML2Plugin
    participant MechanismManager
    participant MechanismDriver

    %% CREATE PORT FLOW
    Client->>NeutronAPI: POST /v2.0/ports
    NeutronAPI->>ML2Plugin: create_port(context)
    ML2Plugin->>ML2Plugin: _create_port_with_binding()
    ML2Plugin->>MechanismManager: bind_port(port_context)
    MechanismManager->>MechanismDriver: attempt to bind (e.g., OVS, SR-IOV)
    MechanismDriver-->>MechanismManager: binding result
    MechanismManager-->>ML2Plugin: port bound
    ML2Plugin-->>NeutronAPI: port with binding details
    NeutronAPI-->>Client: 201 Created + port info

    %% UPDATE PORT FLOW
    Client->>NeutronAPI: PUT /v2.0/ports/{id}
    NeutronAPI->>ML2Plugin: update_port(context)
    ML2Plugin->>ML2Plugin: _update_port_with_binding()
    ML2Plugin->>MechanismManager: bind_port(port_context)
    MechanismManager->>MechanismDriver: rebind or validate existing binding
    MechanismDriver-->>MechanismManager: binding result
    MechanismManager-->>ML2Plugin: updated port context
    ML2Plugin-->>NeutronAPI: port updated
    NeutronAPI-->>Client: 200 OK + updated port info
```

### Bind Port

While `bind_port()` is a distinct method inside of an ML2 mechanism, there is
no direct call for this via the Neutron API. This method is triggered by
Neutron based on certain data provided to port creation and update API calls.

`bind_port()` will be triggered in the following situations:

- the port has a binding host
- the port is either unbound or has previously failed to bind

### Router Interface Lifecycle

When a subnet is attached to a router, the understack ML2 driver sets up a path
so that the Network Node — the host running OVN — can forward traffic on that
network over the physical fabric. This is done through an **uplink port**.

#### The uplink port

The uplink is a Neutron port named `uplink-<segment_id>`. Creating it causes
the OVN mechanism driver to create two OVN Logical Switch Ports (LSPs) on the
network's logical switch:

- `uplink-<segment_id>` — a `localnet`-type LSP created explicitly by understack;
  it connects the logical switch to the physical network via the Network Node's
  trunk VLAN
- `<port-uuid>` — a regular LSP created automatically by the OVN mechanism driver
  when the Neutron port is created

Together they give OVN a way to send and receive that network's traffic over the
Network Node's trunk connection.

The VLAN tag carried on the trunk is *local to the leaf where the Network Node
is connected*. Baremetal nodes connected to different leaves each get their own
per-leaf VLAN segments, which will typically have different VLAN IDs. The
`uplink-<segment_id>` name encodes the segment ID of the Network Node's leaf
segment, making it possible to distinguish it from segments allocated for other
leaves.

```mermaid
flowchart LR
    BM1["Baremetal node<br/>(leaf-1, VLAN 1800)"]
    BM2["Baremetal node<br/>(leaf-2, VLAN 1801)"]
    NN["Network Node / OVN<br/>(leaf-1, VLAN 1802)"]
    LS["OVN Logical Switch<br/>neutron-NETWORK_ID"]

    BM1 -->|"provnet-SEG1<br/>(localnet, tag 1800)"| LS
    BM2 -->|"provnet-SEG2<br/>(localnet, tag 1801)"| LS
    NN -->|"uplink-SEG3<br/>(localnet, tag 1802)"| LS
```

#### Creating the uplink

When `openstack router add subnet` is issued, Neutron creates a router interface
port. The understack driver's `create_port_postcommit()` intercepts this and, if
no other router port already exists on the network, it:

1. Allocates a dynamic VLAN segment on the network-node physnet (the leaf the
   Network Node is connected to)
2. Creates a Neutron port named `uplink-<segment_id>` on that segment
3. Adds that port as a tagged subport on the Network Node's trunk
4. Creates an OVN localnet LSP `uplink-<segment_id>` on the network's logical switch

For VXLAN-type networks a second step runs via the `ROUTER_INTERFACE AFTER_CREATE`
subscription (at `PRIORITY_DEFAULT + 1000`, after OVN's own handler).
`link_vxlan_network_ha_chassis_group()` populates the per-network
`HA_Chassis_Group` from the router's own HCG. This is a workaround for a
Neutron 2026.1 regression where VXLAN gateway networks leave that group empty,
causing ARP and routing to break for baremetal ports on the network.

```mermaid
sequenceDiagram
    participant Client
    participant Neutron
    participant Understack as UnderstackDriver
    participant OVN

    Client->>Neutron: openstack router add subnet
    Neutron->>Understack: create_port_postcommit(router interface port)
    Understack->>Neutron: allocate dynamic VLAN segment (network-node physnet)
    Understack->>Neutron: create Neutron port uplink-SEGMENT_ID
    Understack->>Neutron: add uplink port as trunk subport (tagged VLAN)
    Understack->>OVN: create localnet LSP uplink-SEGMENT_ID

    Note over Neutron,OVN: VXLAN networks only
    Neutron-->>Understack: ROUTER_INTERFACE AFTER_CREATE (priority +1000)
    Understack->>OVN: sync_ha_chassis_group_network_unified
    Understack->>OVN: anchor internal LRP to network HA_Chassis_Group
```

#### Removing the uplink

Cleanup must handle two different Neutron code paths depending on the operation:

| Operation | Neutron internal path | Event received by understack |
|-----------|----------------------|------------------------------|
| `openstack router remove subnet` | `remove_router_interface()` | `ROUTER_INTERFACE AFTER_DELETE` |
| `openstack router delete` | `delete_router()` → `delete_port()` per port | `PORT PRECOMMIT_DELETE` |

`remove_router_interface()` does call `_core_plugin.delete_port()` internally
(see [`l3_db.py#_remove_interface_by_subnet`][l3-db-remove-intf]), but the ML2
plugin only publishes `PORT PRECOMMIT_DELETE` when the port has an ACTIVE
binding record. Router interface ports are not guaranteed to be in that state
at the point `delete_port` is invoked, so the event may silently not fire.
`ROUTER_INTERFACE AFTER_DELETE` is always published by `remove_router_interface()`
regardless of binding state, making it the reliable signal for this path. Both
events are subscribed and both call the shared `_do_uplink_cleanup()` helper.

`_do_uplink_cleanup()` is idempotent: if the shared port is already gone it
returns immediately, so both handlers can fire without double-cleanup.

```mermaid
flowchart TD
    A["openstack router remove subnet"] --> B["ROUTER_INTERFACE<br/>AFTER_DELETE"]
    C["openstack router delete"] --> D["PORT<br/>PRECOMMIT_DELETE"]
    B --> E{Any router ports<br/>still on network?}
    D --> E
    E -- yes --> F([skip — another<br/>router uses this network])
    E -- no --> G["_do_uplink_cleanup()"]
    G --> H["remove trunk subport"]
    G --> I["delete uplink-SEGMENT_ID<br/>OVN localnet LSP"]
    G --> I2["delete shared-port OVN LSP<br/>(port UUID)"]
    G --> J["delete Neutron port DB row<br/>uplink-SEGMENT_ID"]
```

<!-- markdownlint-capture -->
<!-- markdownlint-disable MD046 -->
!!! note "Count semantics differ between the two handlers"

    Both handlers check whether any router ports remain on the network before
    cleaning up. The threshold differs because the deleted port's DB lifetime
    differs by code path:

    - **`PORT PRECOMMIT_DELETE`**: the port is still in the DB at event time,
      so it counts toward the total — cleanup runs when `count ≤ 1`.
    - **`ROUTER_INTERFACE AFTER_DELETE`**: the port is already removed from the
      DB at event time — cleanup runs when `count == 0`.
<!-- markdownlint-restore -->

[networking-baremetal]: <https://docs.openstack.org/networking-baremetal/latest/>
[ovn]: <https://docs.ovn.org/en/latest/>
[ovn-driver]: <https://docs.openstack.org/neutron/latest/ovn/index.html>
[ovn-admin]: <https://docs.openstack.org/neutron/latest/admin/ovn/index.html>
[ovn-routers]: <https://docs.openstack.org/neutron/latest/admin/ovn/refarch/routers.html>
[ovn-router-flavors]: <https://specs.openstack.org/openstack/neutron-specs/specs/2023.2/ml2ovn-router-flavors.html>
[neutron-trunk]: <https://docs.openstack.org/neutron/latest/admin/config-trunking.html>
[neutron-network-segment-range]: <https://docs.openstack.org/neutron/latest/admin/config-network-segment-ranges.html>
[neutron-l2-adjacency]: <https://specs.openstack.org/openstack/neutron-specs/specs/newton/routed-networks.html>
[networking-generic-switch]: <https://docs.openstack.org/networking-generic-switch/latest/>
[ironic-vif-attachment]: <https://docs.openstack.org/ironic/latest/admin/networking.html#vif-attachment-flow>
[ironic-spec-dpa]: <https://review.opendev.org/c/openstack/ironic-specs/+/945642>
[l3-db-remove-intf]: <https://github.com/openstack/neutron/blob/28.0.0/neutron/db/l3_db.py#L1175>
