---
hide:
  - navigation
  - toc
---

# Welcome to UnderStack

<!-- markdownlint-capture -->
<!-- markdownlint-disable MD030 MD032 MD033 MD046 -->
<div class="grid cards" markdown>
-   :material-cloud:{ .lg .middle} __What is UnderStack?__

    [UnderStack](https://github.com/rackerlabs/understack) is an opinionated deployment
    of [OpenStack](https://www.openstack.org/) focused on bare metal provisioning
    through [Ironic](https://docs.openstack.org/ironic/latest/) and its related services.
    This allows for efficiently and consistently managed hardware deployed via API-driven
    workflows across multiple data centers at scale.

    Core requirements include a pool of bare metal systems which can be controlled by
    Ironic as well as switches that can be programmed by a
    [Neutron ML2 driver](https://docs.openstack.org/neutron/latest/admin/config-ml2.html)
    and infrastructure nodes which can host a _Kubernetes_ cluster for the necessary
    services. In our development environment we use Dell servers and Cisco Nexus switches.

-   :material-lightbulb:{ .lg .middle } __Features__

    - OpenStack: Compute, Bare Metal, Network, Load Balancer, Block Storage, Object Storage
    - ArgoCD deployments
    - Nautobot DCIM/IPAM
    - Dex authentication
    - OVN networking
    - Prometheus monitoring and metrics stack

-   :material-map-marker-path:{ .lg .middle } __How this site is arranged__

    Six starting points for five audiences, plus
    [__Reference__](reference/index.md) for lookup. Pick the card below that
    describes what you are doing today — most people need one section and can
    ignore the rest.

    Longer background on the project's goals is in [Vision](vision.md).
</div>
<!-- markdownlint-restore -->

## Where do I start?

<!-- markdownlint-capture -->
<!-- markdownlint-disable MD030 MD032 MD033 MD046 -->
<div class="grid cards" markdown>
-   :material-server-network:{ .lg .middle } __I am standing up a cloud__

    ---

    System operator, day 0. A linear install narrative from requirements through
    to a running site cluster.

    [:octicons-arrow-right-24: Deploy](deploy-guide/welcome.md)

-   :material-lifebuoy:{ .lg .middle } __I am running a cloud__

    ---

    System operator, day 2. Runbooks per service, and a troubleshooting index to
    land on when something is broken.

    [:octicons-arrow-right-24: Operations](operator-guide/index.md)

    [:octicons-arrow-right-24: Troubleshooting](operator-guide/troubleshooting.md)

-   :material-screwdriver:{ .lg .middle } __I am working on a machine__

    ---

    Data centre technician. Enrolling hardware, device types, firmware and BMC
    access for an individual server.

    [:octicons-arrow-right-24: Hardware](operator-guide/hardware.md)

-   :material-lan:{ .lg .middle } __I am working on the network__

    ---

    Network operations. Neutron, OVN and Open vSwitch as they are deployed here,
    and the tenant networking model behind them.

    [:octicons-arrow-right-24: Networking](operator-guide/networking.md)

-   :material-console:{ .lg .middle } __I am using the cloud__

    ---

    Cloud tenant. Driving the OpenStack CLI and APIs to get bare metal servers,
    images and networks.

    [:octicons-arrow-right-24: Using the Cloud](user-guide/index.md)

-   :material-source-branch:{ .lg .middle } __I am changing UnderStack__

    ---

    Contributor. Development environments, how a component becomes an ArgoCD
    `Application`, and how release notes work.

    [:octicons-arrow-right-24: Contributing](contributing/index.md)
</div>
<!-- markdownlint-restore -->
