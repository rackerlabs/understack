# Ironic Inspection Guide

This guide explains how to inspect baremetal nodes in OpenStack Ironic, covering both out-of-band (Redfish) and in-band (Agent) inspection methods.

---

## Overview

UnderStack uses a two-phase inspection process:

1. **Redfish Inspection (Out-of-Band)**: Queries the BMC directly via Redfish API to gather hardware inventory without booting the server
2. **Agent Inspection (In-Band)**: Boots the Ironic Python Agent (IPA) to collect detailed hardware information including LLDP data from network switches

The Argo workflow [inspect-server](https://github.com/rackerlabs/understack/blob/main/workflows/argo-events/workflowtemplates/inspect-server.yaml) automates this process, running both inspection phases sequentially.

---

## Inspection Interfaces

### Redfish / iDRAC-Redfish (Out-of-Band)

Out-of-band inspection queries the BMC directly without booting the server. Use `redfish` for generic Redfish-compliant hardware or `idrac-redfish` for Dell servers.

```bash
# Set the inspect interface
openstack baremetal node set <NODE_UUID_OR_NAME> --inspect-interface idrac-redfish

# Run inspection
openstack baremetal node inspect <NODE_UUID_OR_NAME> --wait
```

**Redfish Inspection Hooks** (configured in `values.yaml`):

```yaml
redfish:
  inspection_hooks: "validate-interfaces,ports,port-bios-name,architecture,pci-devices,resource-class"
```

| Hook | Description |
|------|-------------|
| `validate-interfaces` | Validates discovered network interfaces |
| `ports` | Creates Ironic port objects from Redfish ethernet interfaces |
| `port-bios-name` | Sets port name and `extra.bios_name` from Redfish interface identity (e.g., "NIC.Integrated.1-1") |
| `architecture` | Detects CPU architecture (x86_64, aarch64) |
| `pci-devices` | Discovers PCI devices (GPUs, NICs, storage controllers) |
| `resource-class` | Matches hardware specs against device-types to set the node's resource class |

### Agent (In-Band)

In-band inspection boots the Ironic Python Agent (IPA) ramdisk to collect detailed hardware information, including LLDP data from connected switches.

```bash
# Set the inspect interface
openstack baremetal node set <NODE_UUID_OR_NAME> --inspect-interface agent

# Run inspection
openstack baremetal node inspect <NODE_UUID_OR_NAME> --wait
```

**Agent Inspection Hooks** (configured in `values.yaml`):

```yaml
inspector:
  extra_kernel_params: ipa-collect-lldp=1
  hooks: "ramdisk-error,validate-interfaces,architecture,pci-devices,validate-interfaces,parse-lldp,resource-class,update-baremetal-port"
```

| Hook | Description |
|------|-------------|
| `ramdisk-error` | Reports errors from the IPA ramdisk |
| `validate-interfaces` | Validates discovered network interfaces |
| `architecture` | Detects CPU architecture |
| `pci-devices` | Discovers PCI devices |
| `parse-lldp` | Parses LLDP TLVs to extract switch connection info (switch name, port, chassis ID) |
| `resource-class` | Matches hardware specs against device-types to set the node's resource class |
| `update-baremetal-port` | Updates port `local_link_connection` and `physical_network` from LLDP data |

---

## Automated Inspection Workflow

The `inspect-server` Argo workflow handles the complete inspection process:

1. Reads the node's current driver and provision state
2. Moves the node to `manageable` state if needed
3. Runs Redfish inspection (sets `--inspect-interface redfish` or `idrac-redfish`)
4. Runs Agent inspection (sets `--inspect-interface agent`)
5. Returns the node to its original state

To trigger the workflow manually:

```bash
argo submit -n argo-events --from workflowtemplate/inspect-server -p node=<NODE_UUID_OR_NAME>
```

---

## Viewing Inspection Data

### Node Inventory

After inspection completes, retrieve the full hardware inventory:

```bash
openstack baremetal node inventory save <NODE_UUID_OR_NAME> --file inspection-data.json
```

Sample inventory data:

```json
{
    "inventory": {
        "memory": {
            "physical_mb": 98304
        },
        "cpu": {
            "count": 32,
            "model_name": "AMD EPYC 9124 16-Core Processor",
            "frequency": 4400,
            "architecture": "x86_64"
        },
        "disks": [
            {
                "name": "Solid State Disk 0:1:0",
                "size": 479559942144
            }
        ],
        "interfaces": [
            {
                "mac_address": "D4:CB:E1:BF:8E:21",
                "name": "NIC.Integrated.1-1"
            }
        ],
        "system_vendor": {
            "product_name": "PowerEdge R7615",
            "serial_number": "MXVX4003C100KL",
            "manufacturer": "Dell Inc."
        },
        "boot": {
            "current_boot_mode": "uefi"
        }
    },
    "plugin_data": {
        "parsed_lldp": {
            "eno1": {
                "switch_system_name": "a1-1-1.ord1.rackspace.net",
                "switch_chassis_id": "aa:bb:cc:dd:ee:ff",
                "switch_port_id": "Ethernet1/1"
            }
        }
    }
}
```

### Node Properties and Ports

```bash
# View node details including resource_class and properties
openstack baremetal node show <NODE_UUID_OR_NAME> -f json

# List ports with local_link_connection info
openstack baremetal port list --node <NODE_UUID_OR_NAME> --long
```

### Check Node History

The node history shows recent errors and state transitions:

```bash
openstack baremetal node history list <NODE_UUID_OR_NAME>
```

For detailed error information:

```bash
openstack baremetal node history get <NODE_UUID_OR_NAME> <EVENT_UUID>
```

#### Inspection Timeout

```bash
# Check the node's last error
openstack baremetal node show <NODE_UUID_OR_NAME> -c last_error

# Abort the stuck inspection
openstack baremetal node abort <NODE_UUID_OR_NAME>
```

### Conductor Logs

For deeper investigation, check the Ironic conductor logs:

```bash
kubectl logs -n openstack -l application=ironic,component=conductor --tail=500 | grep <NODE_UUID>
```

---

## Manual Inspection Commands

### Switch Between Inspection Interfaces

```bash
# Use Redfish (out-of-band) inspection
openstack baremetal node set <NODE_UUID_OR_NAME> --inspect-interface redfish

# Use iDRAC-Redfish for Dell servers
openstack baremetal node set <NODE_UUID_OR_NAME> --inspect-interface idrac-redfish

# Use Agent (in-band) inspection
openstack baremetal node set <NODE_UUID_OR_NAME> --inspect-interface agent
```

### Re-run Inspection

```bash
# Ensure node is in manageable state
openstack baremetal node manage <NODE_UUID_OR_NAME> --wait

# Run inspection
openstack baremetal node inspect <NODE_UUID_OR_NAME> --wait

# Return to available state
openstack baremetal node provide <NODE_UUID_OR_NAME> --wait
```
