# OpenStack to Nautobot Synchronization

This guide explains how OpenStack data (Keystone, Neutron, Ironic) is
synchronized to Nautobot and how to handle situations when they get out of sync.

## Event-Driven Sync

Under normal operation, OpenStack data is automatically synchronized to Nautobot
via Oslo notifications. When changes occur, events are published to RabbitMQ
and processed by Argo Events workflows.

### How It Works

1. OpenStack services publish Oslo notifications to RabbitMQ when resources change
2. Argo Events EventSources consume messages from the queues
3. Sensors filter for relevant events and trigger workflows
4. The `openstack-oslo-event` workflow processes the event and updates Nautobot

### Supported Events

The following events trigger Nautobot updates:

| Service | Event Type | Action |
|---------|------------|--------|
| Keystone | `identity.project.created` | Creates tenant in Nautobot |
| Keystone | `identity.project.updated` | Updates tenant in Nautobot |
| Keystone | `identity.project.deleted` | Deletes tenant from Nautobot |
| Neutron | `network.create.end` | Creates UCVNI in Nautobot |
| Neutron | `network.update.end` | Updates UCVNI in Nautobot |
| Neutron | `network.delete.end` | Deletes UCVNI from Nautobot |
| Neutron | `subnet.create.end` | Creates IPAM namespace/prefix in Nautobot |
| Neutron | `subnet.update.end` | Updates IPAM namespace/prefix in Nautobot |
| Neutron | `subnet.delete.end` | Deletes IPAM namespace/prefix from Nautobot |
| Ironic | `baremetal.node.update.end` | Updates device in Nautobot |
| Ironic | `baremetal.node.delete.end` | Deletes device from Nautobot |
| Ironic | `baremetal.node.provision_set.end` | Updates device status and syncs inspection data |
| Ironic | `baremetal.port.create.end` | Creates interface in Nautobot |
| Ironic | `baremetal.port.update.end` | Updates interface in Nautobot |
| Ironic | `baremetal.port.delete.end` | Deletes interface from Nautobot |
| Ironic | `baremetal.portgroup.create.end` | Creates interface in Nautobot |
| Ironic | `baremetal.portgroup.update.end` | Updates interface in Nautobot |
| Ironic | `baremetal.portgroup.delete.end` | Deletes interface from Nautobot |

### Data Synchronized

**Keystone Projects → Nautobot Tenants:**

- Tenant name and description

**Neutron Networks → Nautobot UCVNIs:**

- UCVNI identifier and VLAN segmentation ID
- Associated tenant

**Neutron Subnets → Nautobot IPAM:**

- IPAM namespace per network
- Prefix with CIDR

**Ironic Nodes → Nautobot Devices:**

- Device name (generated from manufacturer and service tag)
- Serial number
- Manufacturer and model
- Hardware specs (memory, CPUs, local storage)
- Provision state (mapped to Nautobot status)
- Location and rack (derived from connected switches)
- Tenant (from Ironic lessee field)
- Network interfaces and their connections

## Bulk Resync

When Nautobot gets out of sync with OpenStack (e.g., after database restore,
missed events, or manual changes), you can perform a bulk resync.

### Dry-Run (Diff Preview)

Before running a resync, you can preview what changes would be made using the
diff workflow. This compares OpenStack and Nautobot data without making changes:

```bash
argo -n argo-events submit --from workflowtemplate/diff-nautobot
```

The diff workflow compares:

- Keystone projects ↔ Nautobot tenants
- Neutron networks ↔ Nautobot UCVNIs
- Neutron subnets ↔ Nautobot prefixes
- Ironic nodes ↔ Nautobot devices

You can also run the diff CLI directly:

```bash
# Compare all projects
uc-diff projects

# Compare all networks
uc-diff network

# Compare all subnets
uc-diff subnets

# Compare all devices
uc-diff devices
```

### Resync Order

The resync workflow runs three steps sequentially in dependency order:

1. **Keystone** - Syncs projects as tenants (must exist before devices reference them)
2. **Neutron** - Syncs networks as UCVNIs and subnets as IPAM namespaces/prefixes
3. **Ironic** - Syncs nodes as devices with interfaces

Each step continues even if the previous step fails.

### Scheduled Resync (CronWorkflow)

A CronWorkflow runs daily at 2:00 AM UTC to catch any drift between OpenStack
and Nautobot. This provides a safety net for missed events.

Check the schedule:

```bash
argo -n argo-events cron list
```

Manually trigger the scheduled workflow:

```bash
argo -n argo-events submit --from cronworkflow/resync-nautobot
```

Suspend/resume the schedule:

```bash
argo -n argo-events cron suspend resync-nautobot
argo -n argo-events cron resume resync-nautobot
```

### On-Demand Resync (WorkflowTemplate)

Resync all OpenStack resources:

```bash
argo -n argo-events submit --from workflowtemplate/resync-nautobot
```

### Using CLI Directly

For debugging or running outside the cluster:

```bash
# Resync all Keystone projects
resync-keystone-nautobot \
  --nautobot_url https://nautobot.example.com \
  --nautobot_token <token>

# Resync all Neutron networks and subnets
resync-neutron-nautobot \
  --nautobot_url https://nautobot.example.com \
  --nautobot_token <token>

# Resync all Ironic nodes
resync-ironic-nautobot \
  --nautobot_url https://nautobot.example.com \
  --nautobot_token <token>
```
