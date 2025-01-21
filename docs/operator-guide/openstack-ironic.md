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
