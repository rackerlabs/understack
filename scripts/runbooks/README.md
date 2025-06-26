# UnderStack Ironic Runbooks

This guide explains how to manage Ironic runbooks in the UnderStack environment for Cleaning & Servicing.

For detailed information, refer to the official OpenStack Ironic runbooks documentation:
 [OpenStack Ironic Runbooks](https://docs.openstack.org/ironic/latest/admin/runbooks.html/)

---

## Check for Existing Runbooks

Before creating a new runbook, verify if it already exists:

```bash
OS_CLOUD=uc-dev-infra baremetal runbook list
```

## Create a New Runbook

```bash
OS_CLOUD=uc-dev-infra baremetal runbook create \
    --name CUSTOM_PXE_INTERFACE_CONFIG \
    --steps scripts/runbooks/bios_pxe_interface_config.yaml
```

## Using a Runbook

```bash
# Using a runbook name
OS_CLOUD=uc-dev-infra baremetal node clean --runbook CUSTOM_PXE_INTERFACE_CONFIG node-0

# Or using a runbook UUID
OS_CLOUD=uc-dev-infra baremetal node clean --runbook 8aba8375-a08b-4e89-9bae-291a8aa100b0 node-0
```
