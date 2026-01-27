# Server Firmware Updates

Currently server firmware updates are performed via Ironic [Runbooks](https://docs.openstack.org/ironic/latest/admin/runbooks.html). For an Ironic Runbook to execute against a node, it requires the node to have a trait with a matching name. These Runbooks can be executed in an Ironic `clean` or `service` step.

## Node Traits

Ironic uses node `trait` matching to provide access control to ensure only approved (matching) `runbooks` are run against the node in question. To list traits for a node, you can run:

```sh
openstack baremetal node show 2a47e27e-e6cc-4e1e-98b0-2ac4778b9014 -c traits -f value
['CUSTOM_FIRMWARE_UPDATE_R7515']
```

Initial `traits` are added during the inspection stage of a node's enrollment, though additional `tratis` can be added with:

`openstack baremetal node add trait 2a47e27e-e6cc-4e1e-98b0-2ac4778b9014 CUSTOM_FIRMWARE_UPDATE_PERC H740P`

## Runbooks

Ironic `runbooks` are used to define which firmware update files are applied, and in what order. You can list existing `runbooks` with:

```sh
openstack baremetal runbook list
+--------------------------------------+------------------------------------+
| UUID                                 | Name                               |
+--------------------------------------+------------------------------------+
| bfd82d37-6093-4307-a504-e844c1f9a5e9 | CUSTOM_FIRMWARE_UPDATE_R7515       |
| 8215b5d0-9607-41e0-8416-9a864841aa60 | CUSTOM_FIRMWARE_UPDATE_R7615       |
| 44aeb02e-5ea8-4a2d-9779-242e009aef76 | CUSTOM_FIRMWARE_UPDATE_R740XD      |
+--------------------------------------+------------------------------------+
```

You can view the contents of a `runbook` with:

```sh
openstack baremetal runbook show CUSTOM_FIRMWARE_UPDATE_R740XD -f yaml
created_at: '2026-01-21T22:13:58+00:00'
disable_ramdisk: false
extra: {}
name: CUSTOM_FIRMWARE_UPDATE_R740XD
owner: 4fa3dd0f57cb3bf331441ed285b27735
public: false
steps:
- args:
    firmware_images:
    - checksum: 4e1243bd22c66e76c2ba9eddc1f91394e57f9f83
      url: http://FILE_SERVER/media/DriversFirmware/Dell_Updates/iDRAC-with-Lifecycle-Controller_Firmware_RVDDR_WN64_7.00.00.181_A00.EXE
      wait: 900
    - checksum: 0e0cf101fa97b8d91b800601ec1abc2552e77227
      url: http://FILE_SERVER/media/DriversFirmware/Dell_Updates/BIOS_J6D53_WN64_2.23.0.EXE
      wait: 300
  interface: management
  order: 1
  step: update_firmware
updated_at: null
uuid: 44aeb02e-5ea8-4a2d-9779-242e009aef76
```

You can execute a runbook against a `node`, with the appropriate matching trait, with:

`openstack baremetal node service --runbook CUSTOM_FIRMWARE_UPDATE_R740XD 62349474-065f-4bb8-9f29-b22c5880c03b`
