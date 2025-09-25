# Ironic Redfish Inspection Guide

This guide explains how to set a Baremetal node in OpenStack Ironic to use the Redfish inspection interface, run inspection, and view the gathered inspection data.

---

## 1. Set the Node to Use Redfish Inspect

First, update the node to use the `redfish` (or vendor-specific, e.g., `idrac-redfish`) inspect interface:

```bash
openstack baremetal node set <NODE_UUID_OR_NAME> --inspect-interface idrac-redfish
```

Note: By default, all our nodes have the following inspection interface:

```json
"inspect_interface": "idrac-redfish"
```

---

## 2. Run Inspection

Trigger inspection on the node:

```bash
openstack baremetal node inspect <NODE_UUID_OR_NAME> --wait
```

This command tells Ironic to boot the node into the inspection environment and gather hardware details via Redfish.

### Argo Workflow Integration

Our Argo [enroll-server](https://github.com/rackerlabs/understack/blob/05b7fb1a8ab9efd3b2f6544b5c62874ed39a3de5/workflows/argo-events/workflowtemplates/enroll-server.yaml#L41) workflow already runs Redfish inspection.
Therefore, just running `openstack baremetal node inventory save` is enough to retrieve the inspection data.

---

## 3. Show Inspection Data

After inspection completes, you can view the data Ironic collected.

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
            },
            {
                "name": "Solid State Disk 0:1:1",
                "size": 479559942144
            }
        ],
        "interfaces": [
            {
                "mac_address": "D4:CB:E1:BF:8E:21"
            },
            {
                "mac_address": "D4:CB:E1:BF:8E:20"
            }
        ],
        "system_vendor": {
            "product_name": "System",
            "serial_number": "MXVX4003C100KL",
            "manufacturer": "Dell Inc."
        },
        "boot": {
            "current_boot_mode": "uefi"
        }
    },
    "plugin_data": {}
}
```

This will save the inspection data (hardware details, NICs, storage, CPU, etc.) to a JSON file.

You can also query directly:

```bash
openstack baremetal node show <NODE_UUID_OR_NAME> -f json
```

Look under fields like `properties`, `extra`, and `driver_internal_info` for inspection results.

---
