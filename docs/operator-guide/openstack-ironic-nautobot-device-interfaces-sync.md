# Ironic to Nautobot Device and Interface Synchronization

This document explains how baremetal server devices and their Ethernet interfaces are automatically created and updated in Nautobot using hardware inspection data from OpenStack Ironic.

## Overview

The integration automatically synchronizes hardware inventory information from Ironic to Nautobot when a baremetal node completes the inspection phase. This ensures that Nautobot maintains an accurate, up-to-date inventory of physical servers and their network connectivity.

## Architecture

The synchronization flow is event-driven and uses the following components:

1. **Server Enrollment Workflow** - Enrolls servers and triggers inspection
2. **OpenStack Ironic** - Performs hardware inspection and publishes Oslo events
3. **Argo Events Sensor** - Listens for specific Ironic events
4. **Argo Workflow** - Orchestrates the synchronization process
5. **Python Workflow Scripts** - Process inspection data and update Nautobot

### Enrollment Workflow Context

The Nautobot synchronization is triggered as part of the broader server enrollment process:

**Workflow:** `enroll-server` (`workflows/argo-events/workflowtemplates/enroll-server.yaml`)

**Steps:**

1. `enroll-server` - Enrolls the server in Ironic using BMC credentials
2. `manage-server` - Transitions node to `manageable` state
3. `redfish-inspect` - **Triggers hardware inspection** (this is where inventory data is collected)
4. `openstack-set-baremetal-node-raid-config` - Configures RAID
5. `inspect-server` - Additional inspection if needed
6. `avail-server` - Makes server available for provisioning

The `redfish-inspect` step executes:

```bash
openstack baremetal node inspect --wait 0 <node-uuid>
```

This inspection triggers the event that causes Nautobot to be updated with the discovered hardware information.

## Event Flow

```text
Server Enrollment → Redfish Inspection → Oslo Event Bus → Argo Events Sensor → Argo Workflow → Update Nautobot
```

### Step-by-Step Process

1. **Server Enrollment**
   - The `enroll-server` workflow is triggered with a BMC IP address
   - Workflow defined in: `workflows/argo-events/workflowtemplates/enroll-server.yaml`
   - Server is enrolled in Ironic and transitioned to `manageable` state

2. **Hardware Inspection**
   - The `redfish-inspect` step executes: `openstack baremetal node inspect --wait 0 <node-uuid>`
   - Ironic performs Redfish-based hardware inspection on the baremetal node
   - Inspection collects: CPU, memory, network interfaces, LLDP neighbor data, BMC information
   - Node transitions from `inspecting` state to `manageable` state

3. **Event Publication**
   - Ironic publishes `baremetal.node.provision_set.end` event to Oslo message bus
   - Event contains node UUID and provision state information
   - Event includes `previous_provision_state: inspecting` in the payload

4. **Event Detection**
   - Argo Events sensor `ironic-oslo-inspecting-event` listens for events
   - Filters for events where `previous_provision_state` was `inspecting`
   - Parses the Oslo message JSON payload

5. **Workflow Trigger**
   - Sensor creates an Argo Workflow named `update-nautobot-*`
   - Workflow uses template `update-nautobot-on-openstack-oslo-event`
   - Event data is passed as workflow parameter

6. **Data Processing**
   - Workflow executes `update-nautobot-on-openstack-oslo-event` script
   - Script fetches full inventory data from Ironic API using node UUID
   - Inventory data is parsed and transformed into Nautobot format

7. **Nautobot Update**
   - Device is created or updated in Nautobot
   - Network interfaces are created with MAC addresses
   - Cables are created based on LLDP neighbor information
   - IP addresses are assigned (for BMC interfaces)

## Configuration Files

### Sensor Configuration

**File:** `components/site-workflows/sensors/sensor-ironic-oslo-inspecting-event.yaml`

The sensor configuration defines:

- Event source: `openstack-ironic`
- Event type filter: `baremetal.node.provision_set.end`
- State filter: `previous_provision_state == "inspecting"`
- Workflow template to trigger

### Workflow Template

**File:** `workflows/argo-events/workflowtemplates/update-nautobot-on-openstack-oslo-event.yaml`

The workflow template:

- Runs the `update-nautobot-on-openstack-oslo-event` command
- Mounts Nautobot token and OpenStack credentials
- Passes event JSON as input file
- Uses service account with appropriate permissions

## Data Processing

### Inventory Data Extraction

**Module:** `understack_workflows.ironic.inventory`

The inventory module performs the following transformations:

#### Interface Name Mapping

Linux interface names from Ironic are converted to Redfish-style names:

| Linux Name | Redfish Name | Description |
|------------|--------------|-------------|
| `eno8303` | `NIC.Embedded.1-1-1` | Embedded NIC port 1 |
| `eno8403` | `NIC.Embedded.2-1-1` | Embedded NIC port 2 |
| `eno3np0` | `NIC.Integrated.1-1` | Integrated NIC port 1 |
| `ens2f0np0` | `NIC.Slot.1-1` | Slot NIC port 1 |

#### LLDP Data Parsing

LLDP (Link Layer Discovery Protocol) data is extracted from inspection results:

- **Chassis ID (Type 1)**: Remote switch MAC address
- **Port ID (Type 2)**: Remote switch port name
- **Port Description (Type 4)**: Alternative port identifier

The system requires a minimum of 3 LLDP neighbors to be discovered for validation.

#### Device Information

The following device attributes are extracted:

- **Manufacturer**: System vendor (e.g., Dell)
- **Model**: Product name
- **Serial Number**: System serial number
- **BMC IP Address**: Out-of-band management IP
- **BIOS Version**: Firmware version
- **Memory**: Total RAM in GiB
- **CPU**: Processor model

### Nautobot Device Creation

**Module:** `understack_workflows.nautobot_device`

#### Device Creation Process

1. **Switch Discovery**
   - Identifies switches using LLDP MAC addresses
   - Queries Nautobot for devices with matching `chassis_mac_address` custom field
   - Validates all switches are in the same location/rack

2. **Device Lookup**
   - Searches for existing device by serial number
   - If not found, creates new device with:
     - Status: "Planned"
     - Role: "server"
     - Location and rack from connected switches
     - Device type based on manufacturer and model

3. **Interface Creation**
   - Creates or updates network interfaces
   - Sets MAC addresses
   - Assigns interface types:
     - BMC interfaces: `1000base-t`
     - Server interfaces: `25gbase-x-sfp28`
   - Sets status to "Active"

4. **Cable Documentation**
   - Creates cables between server and switch interfaces
   - Uses LLDP data to identify correct switch ports
   - Sets cable status to "Connected"

5. **IP Address Assignment**
   - Assigns IP addresses to BMC interfaces
   - Associates IP with interface in Nautobot IPAM
   - Converts DHCP leases to static assignments if applicable

## Validation and Error Handling

### LLDP Neighbor Validation

The system validates that sufficient LLDP neighbors are discovered:

```python
MIN_REQUIRED_NEIGHBOR_COUNT = 3
```

If fewer than 3 neighbors are found, the workflow fails with a detailed error message showing which interfaces have LLDP data.

### Location Consistency

All connected switches must be in the same location and rack. If switches span multiple locations, the workflow fails to prevent topology errors.

### IP Address Conflicts

The system detects and prevents:

- IP addresses already assigned to different interfaces
- Interfaces already associated with different IP addresses

### Switch Port Conflicts

When creating cables, the system validates:

- Switch interface exists in Nautobot
- Switch port is not already connected to another device

## Monitoring and Troubleshooting

### Viewing Workflow Executions

```bash
# List recent workflows
kubectl get workflows -n argo-events | grep update-nautobot

# View workflow details
kubectl describe workflow update-nautobot-<id> -n argo-events

# View workflow logs
kubectl logs -n argo-events <pod-name>
```

## Testing

### Triggering Server Enrollment

To enroll a new server and trigger the complete flow:

```bash
# Submit the enroll-server workflow with BMC IP address
argo -n argo-events submit \
  --from workflowtemplate/enroll-server \
  -p ip_address="10.0.0.100"
```

This will:

1. Enroll the server in Ironic
2. Run hardware inspection (redfish-inspect step)
3. Automatically trigger the Nautobot update via Oslo events

### Manual Inspection Re-trigger

To re-inspect an already enrolled server:

```bash
# Trigger inspection manually
openstack baremetal node inspect --wait <node-uuid>
```

This will publish the Oslo event and trigger Nautobot synchronization.

### Manual Workflow Execution

You can manually trigger the Nautobot update workflow for testing:

```bash
# Capture an event from Ironic
openstack baremetal node show <node-uuid> -f json > node.json

# Submit workflow manually
argo -n argo-events submit \
  --from workflowtemplate/update-nautobot-on-openstack-oslo-event \
  -p event-json "$(cat node.json)"
```

### Verifying Results

After workflow execution, verify in Nautobot:

1. Device exists with correct serial number
2. Device is in correct location/rack
3. All network interfaces are created
4. MAC addresses are correct
5. Cables connect to correct switch ports
6. BMC interface has IP address assigned

## Related Components

- **Ironic Client** (`understack_workflows.ironic.client`): Wrapper for Ironic API
- **Chassis Info** (`understack_workflows.bmc_chassis_info`): Data models for hardware info
- **Nautobot Device** (`understack_workflows.nautobot_device`): Nautobot API operations

## References

- [PR #1361](https://github.com/rackerlabs/understack/pull/1361) - Implementation details
