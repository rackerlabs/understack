# IronicRunbook Examples

Reference CRs for the `ironicRunbooks` openstack-sync hook. **Nothing here is
applied.** The parent `kustomization.yaml` lists only the shared runbooks, and
this directory is not one of its `resources`.

## Using one

Copy the file to where the CRs for your site live, usually
`<deploy-repo>/<site>/openstack-sync-plugins/`, add it to that directory's
`kustomization.yaml`, then adjust three things:

1. `metadata.namespace`: must be the namespace the operator watches
   (`POD_NAMESPACE`, commonly `openstack`). The samples use
   `baremetal-system` and `default`, which the hook will not see.
2. `spec.cloudCredentialsRef`: the Secret holding `clouds.yaml` and the cloud
   entry to authenticate with.
3. `spec.traits`: Ironic only runs a runbook on a node carrying at least one of
   them, so a runbook with no traits matches no nodes.

Step names and arguments in these files are illustrative. Check that the
`interface` and `step` you want exist on the target hardware before relying on
them, and replace the firmware URLs and checksums with real ones.

## Removing one

Deleting the CR does not delete the Ironic runbook. The hook only prunes when
`PRUNE` is enabled for it, and the chart default is `false`, so a removed CR
leaves the runbook in Ironic with nothing reconciling it. Delete both, or turn
pruning on deliberately — see
`docs/operator-guide/server-firmware-update.md#removing-a-runbook`.

## The examples

| File | Purpose |
|------|---------|
| `runbook_v1alpha1_minimal.yaml` | Smallest valid CR: required fields only |
| `runbook_v1alpha1_complete.yaml` | Every field, with each one annotated |
| `runbook_bios_config.yaml` | BIOS settings for virtualization on compute nodes |
| `runbook_raid_config.yaml` | RAID setup, OS volume plus data volume |
| `runbook_firmware_update.yaml` | BIOS, BMC and NIC firmware updates |
| `runbook_disk_cleaning.yaml` | Disk erasure for node reuse |
| `runbook_gpu_node_setup.yaml` | BIOS and firmware for GPU nodes |

## Validation

Editors pick up the published spec schema from the `yaml-language-server` line at
the top of `../bmc_maintenance.yaml`; add the same line to a copied example to
get completion and checking. Kubernetes validates the full CR against the CRD in
`components/openstack-sync-operator/crds/` when ArgoCD applies it.

Running a synced firmware runbook against a node is covered in
`docs/operator-guide/server-firmware-update.md`.
