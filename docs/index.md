---
hide:
  - navigation
  - toc
---

# Welcome to UnderStack

<!-- markdownlint-capture -->
<!-- markdownlint-disable MD030 MD032 MD033 MD046 -->
<div class="grid cards" markdown>
-   :material-cloud:{ .lg} __What is UnderStack?__

    UnderStack is an opinionated deployment of OpenStack focused on bare metal
    provisioning through Ironic and its related services. This allows for efficiently
    and consistently managed hardware deployed via API-driven workflows across multiple
    data centers at scale.

    Core requirements include a pool of bare metal systems which can be controlled by
    Ironic as well as switches that can be programmed by a Neutron ML2 driver and
    infrastructure nodes which can host a Kubernetes cluster for the necessary services.

    The documentation covers both Kubernetes cluster deployment options and configuration
    of the UnderStack components for bare metal resource management in a multi-data center
    environment.

-   :material-abacus:{ .xl .middle } __Getting Started__

    See our [Deploy Guide](deploy-guide/welcome.md) to begin with your own deployment.
</div>
<!-- markdownlint-restore -->
