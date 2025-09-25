# Runbook: Configure Dell Node Boot Interface (HTTP/iPXE)

**Goal:** Ensure Dell baremetal nodes are configured to boot with `http-ipxe` (with PXE fallback enabled).
**Applies To:** Dell nodes managed via OpenStack Ironic.

## TL;DR

```bash
openstack baremetal node manage <NODE>
openstack baremetal node clean --clean-steps dell-boot-config.yaml <NODE>
openstack baremetal node set --boot-interface http-ipxe <NODE>
openstack baremetal node provide <NODE>
```

---

## Step 1: Put node into manageable state

```bash
openstack baremetal node manage <NODE>
```

---

## Step 2: Apply BIOS configuration

Save `dell-boot-config.yaml`:

```yaml
---
- interface: bios
  step: apply_configuration
  args:
    settings:
      - name: PxeDev1EnDis
        value: Enabled
      - name: PxeDev1Interface
        value: NIC.Slot.1-1
      - name: HttpDev1EnDis
        value: Enabled
      - name: HttpDev1Interface
        value: NIC.Slot.1-1
      - name: HttpDev1TlsMode
        value: None
      - name: TimeZone
        value: UTC
  order: 1
```

Run cleaning with the runbook:

```bash
openstack baremetal node clean \
  --clean-steps dell-boot-config.yaml \
  <NODE>
```

---

## Step 3: Monitor Cleaning Progress

```bash
openstack baremetal node show <NODE> -f value -c provision_state
```

Check the provision state until it returns to `manageable`:

Expected transitions:

- `cleaning`
- `clean wait`
- `manageable`

---

- If provision_state is `clean failed`: check the error

  ```bash
  openstack baremetal node show <NODE> -f value -c last_error
  ```

---

## Step 4: Switch node to HTTP iPXE boot

```bash
openstack baremetal node set --boot-interface http-ipxe <NODE>
```

---

## Step 5: Provide the node (make it available)

```bash
openstack baremetal node provide <NODE>
```

---

### (Optional) We can also use runbooks for Cleaning & Servicing

For detailed information, refer to the official OpenStack Ironic runbooks documentation:
[OpenStack Ironic Runbooks](https://docs.openstack.org/ironic/latest/admin/runbooks.html/)

To run these commands [baremetal Standalone Command-Line Interface (CLI)](https://docs.openstack.org/python-ironicclient/latest/cli/standalone.html) is required

### Check for Existing Runbooks

Before creating a new runbook, verify if it already exists:

```bash
baremetal runbook list
```

### Create a New Runbook

```bash
baremetal runbook create \
    --name CUSTOM_PXE_INTERFACE_CONFIG \
    --steps scripts/runbooks/bios_pxe_interface_config.yaml
```

[scripts/runbooks/bios_pxe_interface_config.yaml](https://raw.githubusercontent.com/rackerlabs/understack/refs/heads/main/scripts/runbooks/bios_pxe_interface_config.yaml)

### Using a Runbook

```bash
# Using a runbook name
baremetal node clean --runbook CUSTOM_PXE_INTERFACE_CONFIG node-0

# Or using a runbook UUID
baremetal node clean --runbook 8aba8375-a08b-4e89-9bae-291a8aa100b0 node-0
```

---
