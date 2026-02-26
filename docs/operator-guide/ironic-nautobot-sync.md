# Ironic to Nautobot Synchronization

This guide explains how OpenStack Ironic data is synchronized to Nautobot
and how to handle situations when they get out of sync.

## Event-Driven Sync

Under normal operation, Ironic data is automatically synchronized to Nautobot
via Oslo notifications. When changes occur in Ironic, events are published to
RabbitMQ and processed by Argo Events workflows.

### How It Works

1. Ironic publishes Oslo notifications to RabbitMQ when nodes change
2. An Argo Events EventSource consumes messages from the `ironic` queue
3. A Sensor filters for relevant events and triggers workflows
4. The `openstack-oslo-event` workflow processes the event and updates Nautobot

### Supported Events

The following Ironic events trigger Nautobot updates:

| Event Type | Action |
|------------|--------|
| `baremetal.node.create.end` | Creates device in Nautobot |
| `baremetal.node.update.end` | Updates device in Nautobot |
| `baremetal.node.delete.end` | Deletes device from Nautobot |
| `baremetal.node.provision_set.end` | Updates device status and syncs inspection data |
| `baremetal.port.create.end` | Creates interface in Nautobot |
| `baremetal.port.update.end` | Updates interface in Nautobot |
| `baremetal.port.delete.end` | Deletes interface from Nautobot |

### Data Synchronized

For each Ironic node, the following data is synced to Nautobot:

- Device name (generated from manufacturer and service tag)
- Serial number
- Manufacturer and model
- Hardware specs (memory, CPUs, local storage)
- Provision state (mapped to Nautobot status)
- Location and rack (derived from connected switches)
- Tenant (from Ironic lessee field)
- Network interfaces and their connections

## Bulk Resync

When Nautobot gets out of sync with Ironic, you can perform a bulk resync.

### Scheduled Resync (CronWorkflow)

A CronWorkflow runs daily at 2:00 AM UTC to catch any drift between Ironic
and Nautobot. This provides a safety net for missed events.

Check the schedule:

```bash
argo -n argo-events cron list
```

Manually trigger the scheduled workflow:

```bash
argo -n argo-events submit --from cronworkflow/resync-ironic-nautobot
```

Suspend/resume the schedule:

```bash
argo -n argo-events cron suspend resync-ironic-nautobot
argo -n argo-events cron resume resync-ironic-nautobot
```

### On-Demand Resync (WorkflowTemplate)

Resync all nodes:

```bash
argo -n argo-events submit --from workflowtemplate/resync-ironic-nautobot
```

Resync a specific node:

```bash
argo -n argo-events submit --from workflowtemplate/resync-ironic-nautobot \
  -p node="<node-uuid>"
```

### Using CLI Directly

For debugging or running outside the cluster:

```bash
# Resync all nodes
resync-ironic-nautobot \
  --nautobot_url https://nautobot.example.com \
  --nautobot_token <token>

# Resync a specific node
resync-ironic-nautobot \
  --node <uuid> \
  --nautobot_url https://nautobot.example.com \
  --nautobot_token <token>

# Dry run to see what would be synced
resync-ironic-nautobot \
  --dry-run \
  --nautobot_url https://nautobot.example.com \
  --nautobot_token <token>
```
