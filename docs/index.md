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

-   :material-abacus:{ .lg .middle } __Getting Started__

    The documentation covers both Kubernetes cluster deployment options and configuration
    of the UnderStack components for bare metal resource management in a multi-data center
    environment.

    See our [Deploy Guide](deploy-guide/welcome.md) to begin your own deployment.
</div>
<!-- markdownlint-restore -->
