# Ironic Runbook Kubernetes CRD

Kubernetes Custom Resource Definition (CRD) for managing Ironic baremetal runbooks. Runbooks define automated sequences of operations (cleaning, configuration, firmware updates) to be executed on baremetal nodes.

## What is a Runbook?

A Runbook is a collection of ordered steps that define automated operations on baremetal nodes in Ironic. Runbooks enable:

- **Automated Cleaning**: Prepare nodes for reuse (disk wiping, BIOS config, firmware updates)
- **Declarative Workflows**: Define repeatable, version-controlled sequences
- **Trait-Based Matching**: Runbooks match to nodes when the runbook name matches a node trait

## Quick Start

### Installation

```bash
# Install the CRD
kubectl apply -f bases/baremetal.ironicproject.org_runbooks.yaml
```

### Create Your First Runbook

```bash
# Apply a minimal example
kubectl apply -f samples/runbook_v1alpha1_minimal.yaml

# Verify it was created
kubectl get runbooks
kubectl describe runbook minimal-runbook
```

### View Available Samples

```bash
# List all sample runbooks
ls samples/

# Apply a specific sample
kubectl apply -f samples/runbook_bios_config.yaml
```

## Field Requirements

### ✅ Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `spec.runbookName` | string | Runbook name matching CUSTOM_* pattern |
| `spec.steps` | array | Ordered list of steps (minimum 1) |
| `steps[].interface` | enum | Hardware interface (bios, raid, deploy, etc.) |
| `steps[].step` | string | Step name (non-empty) |
| `steps[].order` | integer | Execution order (>= 0, unique) |

### ❌ Optional Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `spec.disableRamdisk` | boolean | `false` | Skip ramdisk booting |
| `spec.public` | boolean | `false` | Public accessibility |
| `spec.owner` | string | `null` | Project/tenant owner |
| `spec.extra` | object | `{}` | Additional metadata |
| `steps[].args` | object | `{}` | Step-specific arguments |

## Minimal Example

```yaml
apiVersion: baremetal.ironicproject.org/v1alpha1
kind: IronicRunbook
metadata:
  name: minimal-runbook
  namespace: default
spec:
  runbookName: CUSTOM_MINIMAL
  steps:
    - interface: deploy
      step: erase_devices
      order: 1
```

## Sample Runbooks

| Sample | Use Case | Description |
|--------|----------|-------------|
| `runbook_v1alpha1_minimal.yaml` | Learning | Minimal example with required fields only |
| `runbook_v1alpha1_complete.yaml` | Reference | Complete example with all fields |
| `runbook_bios_config.yaml` | Compute Nodes | BIOS configuration for virtualization |
| `runbook_raid_config.yaml` | Storage Nodes | RAID setup (OS + data volumes) |
| `runbook_firmware_update.yaml` | Maintenance | Firmware updates (BIOS, BMC, NIC) |
| `runbook_disk_cleaning.yaml` | Node Reuse | Secure disk erasure |
| `runbook_gpu_node_setup.yaml` | ML/AI | GPU node configuration |

## Running a Runbook

Once the operator syncs the CRD into Ironic, you execute a runbook by
transitioning a node into the `clean` provisioning state with the runbook
specified. The node must be in `manageable` state before you can trigger
cleaning.

### OpenStack CLI

```bash
# Run a runbook by name
openstack baremetal node clean <node-uuid> --runbook CUSTOM_BMC_MAINTENANCE

# Check node state while cleaning runs
openstack baremetal node show <node-uuid> -f value -c provision_state
```

### Python SDK

```python
from understack_workflows.ironic_node import transition

# node must already be in manageable state
transition(
    node,
    "clean",
    expected_state="manageable",
    runbook=runbook_uuid,
)
```

The `transition` helper calls `set_node_provision_state` and waits for the
node to return to `manageable` once all steps complete.

### Trait-Based Automatic Execution

Runbooks can also be triggered automatically by matching node traits. Add the
runbook name as a trait on the node:

```bash
openstack baremetal node add trait <node-uuid> CUSTOM_BMC_MAINTENANCE
```

Workflow code (e.g. `apply_firmware_updates` in `ironic_node.py`) can then
discover matching traits and execute the corresponding runbooks in order.

## Support

- **Ironic Documentation**: https://docs.openstack.org/ironic/latest/
- **Kubernetes CRDs**: https://kubernetes.io/docs/tasks/extend-kubernetes/custom-resources/

---

**Version**: v1alpha1
**API Group**: baremetal.ironicproject.org
**Kind**: IronicRunbook
**Short Name**: rb
