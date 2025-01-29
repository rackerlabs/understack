# Ironic

## Setting baremetal node flavor

Upstream docs: <https://docs.openstack.org/ironic/latest/install/configure-nova-flavors.html>

When creating a flavor, make sure to include a property for the baremetal custom flavor,
which in this example is `resources:CUSTOM_BAREMETAL_GP2SMALL=1`:

``` bash
openstack --os-cloud understack flavor create \
    --ram 98304 --disk 445 --vcpus 32 --public \
    --property resources:CUSTOM_BAREMETAL_GP2SMALL=1 \
    --property resources:DISK_GB=0 \
    --property resources:MEMORY_MB=0 \
    --property resources:VCPU=0 gp2.small
```

Then set the baremetal node's resource class with the custom flavor:

``` bash
openstack baremetal node set 8d15b1b4-e3d8-46c3-bcaa-5c50cd5d1f5b --resource-class baremetal.gp2small
```

## Cleaning a baremetal node

Create a baremetal raid config file for a raid1 config with the following contents:

``` json title="raid1-config.json"
{ "logical_disks":
  [ { "controller": "RAID.SL.1-1",
      "is_root_volume": true,
      "physical_disks": [
          "Disk.Bay.0:Enclosure.Internal.0-1:RAID.SL.1-1",
          "Disk.Bay.1:Enclosure.Internal.0-1:RAID.SL.1-1"
      ],
      "raid_level": "1",
      "size_gb": "MAX"
    }
  ]
}
```

Apply the raid1 config from above:

``` bash
openstack baremetal node set ${NODE_UUID} --target-raid-config raid1-config.json
```

Create another file with our node cleaning steps:

``` json title="raid-clean-steps.json"
[{
  "interface": "raid",
  "step": "delete_configuration"
},
{
  "interface": "raid",
  "step": "create_configuration"
}]
```

Clean the node:

``` bash
openstack baremetal node clean --clean-steps raid-clean-steps.json --disable-ramdisk ${NODE_UUID}
```

## Troubleshooting Ironic Nodes

### Node History

Upstream docs: <https://docs.openstack.org/ironic/latest/admin/node-history.html>

You can quickly see a bare metal node's history using the ironic CLI and the `openstack baremetal node history list <node>` command:

``` console
openstack baremetal node history list Dell-ABC1234
+--------------------------------------+---------------------------+----------+--------------------------------------------------------------------------------------------------------------------------------+
| UUID                                 | Created At                | Severity | Description of the event                                                                                                       |
+--------------------------------------+---------------------------+----------+--------------------------------------------------------------------------------------------------------------------------------+
| b562fa2e-27e9-47c6-ad1b-7be27cdee821 | 2025-01-15T23:39:20+00:00 | ERROR    | Timeout reached while cleaning the node. Please check if the ramdisk responsible for the cleaning is running on the node.      |
|                                      |                           |          | Failed on step {}.                                                                                                             |
| e717fcd0-cb47-482d-93af-996a42183b10 | 2025-01-17T19:38:04+00:00 | ERROR    | Failed to prepare node 2e32caa9-482a-4ca1-a16b-3dcc164e696c for cleaning: Failed to create neutron ports for node's            |
|                                      |                           |          | 2e32caa9-482a-4ca1-a16b-3dcc164e696c ports                                                                                     |
|                                      |                           |          | [Port(address=11:22:33:44:55:66,created_at=2025-01-14T15:49:12Z,extra={},id=563,internal_inf...                                |
| 6c5727ef-96a6-414d-8599-01cf3fc06427 | 2025-01-17T19:40:58+00:00 | ERROR    | Failed to prepare node 2e32caa9-482a-4ca1-a16b-3dcc164e696c for cleaning: Failed to create neutron ports for node's            |
|                                      |                           |          | 2e32caa9-482a-4ca1-a16b-3dcc164e696c ports                                                                                     |
|                                      |                           |          | [Port(address=11:22:33:44:55:66,created_at=2025-01-14T15:49:12Z,extra={},id=563,internal_inf...                                |
| 8d72ed0c-d61d-4254-bc7e-891098431195 | 2025-01-17T20:24:14+00:00 | ERROR    | Timeout reached while cleaning the node. Please check if the ramdisk responsible for the cleaning is running on the node.      |
|                                      |                           |          | Failed on step {}.                                                                                                             |
| 2ceab449-2f4e-4c47-b123-ef83591d42bc | 2025-01-17T22:12:14+00:00 | ERROR    | Timeout reached while cleaning the node. Please check if the ramdisk responsible for the cleaning is running on the node.      |
|                                      |                           |          | Failed on step {}.                                                                                                             |
| c6b675e8-d46f-4a71-be6c-04a6a13c0877 | 2025-01-20T11:52:23+00:00 | ERROR    | Timeout reached while cleaning the node. Please check if the ramdisk responsible for the cleaning is running on the node.      |
|                                      |                           |          | Failed on step {}.                                                                                                             |
| ef24d307-1b74-4178-9565-80520d75e6ab | 2025-01-20T12:25:24+00:00 | ERROR    | Timeout reached while cleaning the node. Please check if the ramdisk responsible for the cleaning is running on the node.      |
|                                      |                           |          | Failed on step {}.                                                                                                             |
| 557f08fc-7d48-45b4-95d3-c9ae8efc195e | 2025-01-20T12:59:23+00:00 | ERROR    | Timeout reached while cleaning the node. Please check if the ramdisk responsible for the cleaning is running on the node.      |
|                                      |                           |          | Failed on step {}.                                                                                                             |
| 1aa57c41-1320-4b22-94d8-c254e43b3a0e | 2025-01-20T16:02:25+00:00 | ERROR    | Timeout reached while cleaning the node. Please check if the ramdisk responsible for the cleaning is running on the node.      |
|                                      |                           |          | Failed on step {}.                                                                                                             |
| 3956ea6c-c4d2-4808-9608-330bfcc06a63 | 2025-01-22T18:41:56+00:00 | ERROR    | Deploy step deploy.switch_to_tenant_network failed: Error changing node 2e32caa9-482a-4ca1-a16b-3dcc164e696c to tenant         |
|                                      |                           |          | networks after deploy. NetworkError: Could not add public network VIF fc9fa869-9d18-49a5-858f-c7a2da4a2b4e to node             |
|                                      |                           |          | 2e32caa9-482a-4ca...                                                                                                           |
+--------------------------------------+---------------------------+----------+--------------------------------------------------------------------------------------------------------------------------------+
```

You can then show the full event details with `openstack baremetal node history get <node> <event>` where the event ID is from the UUID column of the previous command:

``` console
openstack baremetal node history get Dell-ABC1234 3956ea6c-c4d2-4808-9608-330bfcc06a63
+------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| Field      | Value                                                                                                                                                                                           |
+------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| conductor  | conductor-3                                                                                                                                                                                     |
| created_at | 2025-01-22T18:41:56+00:00                                                                                                                                                                       |
| event      | Deploy step deploy.switch_to_tenant_network failed: Error changing node 2e32caa9-482a-4ca1-a16b-3dcc164e696c to tenant networks after deploy. NetworkError: Could not add public network VIF    |
|            | fc9fa869-9d18-49a5-858f-c7a2da4a2b4e to node 2e32caa9-482a-4ca1-a16b-3dcc164e696c, possible network issue. HttpException: 500: Server Error for url: http://neutron-                            |
|            | server.openstack.svc.cluster.local:9696/v2.0/ports/fc9fa869-9d18-49a5-858f-c7a2da4a2b4e, Nautobot error                                                                                         |
| event_type | deploying                                                                                                                                                                                       |
| severity   | ERROR                                                                                                                                                                                           |
| user       | None                                                                                                                                                                                            |
| uuid       | 3956ea6c-c4d2-4808-9608-330bfcc06a63                                                                                                                                                            |
+------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
```

With this output we can see there was an issue in Nautobot which gave an unexpected 503 error and we should investigate further there.
