# Troubleshooting

Somewhere to land from a pager. Troubleshooting material is spread across this
site by subsystem; this page is the index into it.

!!! tip "If you deploy from `main`"
    Before anything else, check the
    [Unreleased release notes](../release-notes/unreleased.md). A deployment
    tracking `HEAD` picks up changes continuously, and a change that needed
    operator action is the most likely explanation for something that worked
    yesterday.

## Start from the symptom

| Symptom | Go to |
| --- | --- |
| ArgoCD `Application` stuck syncing, or a sync hook job looping | [Deployment Troubleshooting](../deploy-guide/troubleshooting.md) |
| An OpenStack service will not start, or a chart will not render | [Troubleshooting OpenStack Helm](troubleshooting-osh.md) |
| `NeutronAgentDown`, or tenant traffic not passing | [OVN / Open vSwitch](ovs-ovn.md) |
| A router port is bound to the wrong chassis | [OVN / Open vSwitch](ovs-ovn.md#verifying-a-router-port-is-bound-to-an-ha_chassis_group) |
| A baremetal node is stuck in `clean wait`, `deleting` or `error` | [Baremetal Box Cleanup Runbook](baremetal-ironic-cleanup-runbook.md) |
| Inspection is failing or returning nothing | [Ironic Inspection Guide](openstack-ironic-inspection-guide.md) |
| A node will not PXE boot, or boots the wrong way | [Change Boot Interface](openstack-ironic-change-boot-interface.md) |
| A workflow failed, or a sensor is not firing | [Argo Workflows](workflows.md#troubleshooting) |
| Nautobot and OpenStack disagree about a resource | [OpenStack to Nautobot Sync](openstack-nautobot-sync.md) |
| You need to back up or restore an OpenStack MariaDB database | [MariaDB Operator](mariadb-operator.md) |
| You need to inspect or back up the Nautobot PostgreSQL database | [Postgres Operator](postgres-operator.md) |
| A service cannot reach RabbitMQ | [RabbitMQ](rabbitmq.md) |
| You need access to the Ceph dashboard | [Rook Ceph](rook-ceph.md) |
| A URL 404s, or TLS is wrong on an endpoint | [Gateway API](gateway-api.md) |
| An mTLS client is being rejected by Nautobot | [Nautobot mTLS Certificate Renewal](nautobot-mtls-certificate-renewal.md) |
| You need the generated password for a server's BMC | [BMC Password](bmc-password.md) |

## Working out what happened

- [OpenStack Logging](logging.md) — how to read an OpenStack log line, which is
  the difference between a request id you can trace and a wall of text.
- [Monitoring Stack](monitoring.md) — reaching Prometheus and AlertManager, and
  what the shipped alerts mean.
- [kubectl-us-net](kubectl-us-net.md) — inspecting UnderStack networking objects
  from `kubectl` rather than through the OpenStack API, which is what you want
  when the API itself is the thing that is broken.

## Before you escalate

Have these ready, because they are the first things you will be asked for:

1. The cluster, and whether it is a global or site cluster.
2. The deployed revision — the `understack_ref` in your deploy repository, and
   the commit ArgoCD actually has synced. These are not always the same.
3. The failing resource's identifier: node UUID, port id, `Application` name, or
   workflow name.
4. Whether it ever worked, and what changed if so.

## Something missing here?

This page is only as good as its coverage. If you worked out a failure mode that
is not listed, add the row — and if the page it should point at does not exist,
that is worth saying too. See
[Contributing](../contributing/index.md).
