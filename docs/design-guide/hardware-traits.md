# Hardware Traits

## Purpose

Hardware traits are characteristics discovered during inspection that describe capabilities or features of bare metal nodes. Traits enable flavor definitions to filter nodes based on specific hardware attributes beyond basic resource class matching.

Traits follow a hybrid model:

* **Standard traits**: Common, well-defined traits with consistent discovery logic
* **Custom traits**: Site-specific or vendor-specific traits following naming conventions

## Trait Naming Convention

All trait names in UnderStack follow these rules:

* Uppercase alphanumeric characters with underscores only (pattern: `^[A-Z][A-Z0-9_]*$`)
* Written without `CUSTOM_` prefix in flavor definitions (prefix added automatically when interacting with Ironic)
* Descriptive and concise (e.g., `NVME`, not `HAS_NVME_STORAGE_CAPABILITY`)
* Category-based prefixes for organization (e.g., `NIC_`, `GPU_`, `CPU_`)

**Good trait names:**

* `NVME` - Node has NVMe storage
* `GPU_NVIDIA` - Node has NVIDIA GPU
* `NIC_MELLANOX` - Node has Mellanox network card
* `CPU_AVX512` - CPU supports AVX-512 instructions

**Poor trait names:**

* `nvme` - Not uppercase
* `has-nvme` - Contains hyphens
* `CUSTOM_NVME` - Includes CUSTOM_ prefix (added automatically)

## Standard Traits

Standard traits are commonly used across deployments and have well-defined discovery logic.

### Storage Traits

* **NVME**: Node has at least one NVMe storage device
    * Discovery: Check for NVMe devices in `/sys/class/nvme/` or block device type
* **RAID**: Node has hardware RAID controller
    * Discovery: Detect RAID controller via lspci or vendor-specific tools
* **SSD**: Node has at least one SSD (non-NVMe)
    * Discovery: Check block device rotational flag

### Network Traits

* **NIC_MELLANOX_CX5**: Node has Mellanox ConnectX-5 network interface
    * Discovery: Check NIC vendor ID (0x15b3) and device ID (0x1017 for ConnectX-5)
* **NIC_INTEL_X710**: Node has Intel X710 network interface
    * Discovery: Check NIC vendor ID (0x8086) and device ID (0x1572 for X710-DA4)
* **NIC_BROADCOM_57414**: Node has Broadcom BCM57414 network interface
    * Discovery: Check NIC vendor ID (0x14e4) and device ID (0x16d7 for BCM57414)
* **NIC_25G**: Node has 25 Gbps capable network interface
    * Discovery: Check link speed capability
* **NIC_100G**: Node has 100 Gbps capable network interface
    * Discovery: Check link speed capability

### GPU Traits

* **GPU**: Node has GPU device
    * Discovery: Check for GPU PCI device class (0x0300)
* **GPU_NVIDIA**: Node has NVIDIA GPU
    * Discovery: Check GPU vendor ID (0x10de)
* **GPU_AMD**: Node has AMD GPU
    * Discovery: Check GPU vendor ID (0x1002)

### CPU Traits

* **CPU_AVX512**: CPU supports AVX-512 instruction set
    * Discovery: Check CPU flags for avx512
* **CPU_SGX**: CPU supports Intel SGX
    * Discovery: Check CPU flags for sgx
* **CPU_AMD**: CPU is AMD processor
    * Discovery: Check CPU vendor string
* **CPU_INTEL**: CPU is Intel processor
    * Discovery: Check CPU vendor string

### Firmware/BIOS Traits

* **SECURE_BOOT**: Node has Secure Boot enabled
    * Discovery: Check UEFI Secure Boot status
* **TPM**: Node has TPM (Trusted Platform Module)
    * Discovery: Check for TPM device in `/sys/class/tpm/`

## Custom Traits

Custom traits allow site-specific or vendor-specific hardware categorization not covered by standard traits.

### Use Cases for Custom Traits

* **Hardware generations**: `GEN10`, `GEN11` for HP server generations
* **Vendor-specific features**: `IDRAC9`, `ILO5` for management interfaces

### Custom Trait Guidelines

* Use clear, descriptive names
* Document trait meaning in deployment repository
* Include discovery logic in inspection hook
* Avoid overlapping with standard traits
* Consider whether trait should become standard if widely used

## Trait Discovery

Traits are added to Ironic nodes during the inspection process via inspection hooks in `python/ironic-understack`.

### Inspection Hook Pattern

```python
from ironic.drivers.modules.inspector.hooks import base
from oslo_log import log as logging

LOG = logging.getLogger(__name__)

class TraitDiscoveryHook(base.InspectionHook):
    """Hook to discover and add hardware traits to nodes."""

    def __call__(self, task, inventory, plugin_data):
        """Discover traits from hardware inventory."""
        traits = set()

        # Example: Detect NVMe storage
        if self._has_nvme_storage(inventory):
            traits.add('CUSTOM_NVME')

        # Example: Detect GPU
        if self._has_gpu(inventory):
            traits.add('CUSTOM_GPU')
            gpu_vendor = self._get_gpu_vendor(inventory)
            if gpu_vendor == 'nvidia':
                traits.add('CUSTOM_GPU_NVIDIA')

        # Add discovered traits to node
        if traits:
            task.node.set_trait(list(traits))
            LOG.info("Added traits to node %s: %s", task.node.uuid, traits)

    def _has_nvme_storage(self, inventory):
        """Check if node has NVMe storage."""
        for disk in inventory.get('disks', []):
            if 'nvme' in disk.get('name', '').lower():
                return True
        return False

    def _has_gpu(self, inventory):
        """Check if node has GPU."""
        for pci in inventory.get('pci_devices', []):
            # PCI class 0x0300 is VGA compatible controller
            if pci.get('class_id') == '0x0300':
                return True
        return False

    def _get_gpu_vendor(self, inventory):
        """Determine GPU vendor."""
        for pci in inventory.get('pci_devices', []):
            if pci.get('class_id') == '0x0300':
                vendor_id = pci.get('vendor_id')
                if vendor_id == '0x10de':
                    return 'nvidia'
                elif vendor_id == '0x1002':
                    return 'amd'
        return None
```

### Trait Discovery Best Practices

* **Idempotent**: Running inspection multiple times should produce same traits
* **Accurate**: Only add traits that are definitively present
* **Documented**: Document discovery logic for each trait
* **Efficient**: Minimize expensive hardware probing
* **Testable**: Include unit tests for trait discovery logic

## Trait Usage in Flavors

Flavors reference traits to filter nodes within a resource class.

### Requiring Specific Hardware

```yaml
name: compute.nvme
resource_class: m1.medium
traits:
  - trait: NVME
    state: required
```

Matches only nodes with NVMe storage in m1.medium resource class.

### Excluding Hardware

```yaml
name: compute.no-gpu
resource_class: m1.large
traits:
  - trait: GPU
    state: absent
```

Matches nodes without GPU in m1.large resource class.

### Multiple Trait Requirements

```yaml
name: compute.nvidia-nvme
resource_class: m1.large
traits:
  - trait: GPU_NVIDIA
    state: required
  - trait: NVME
    state: required
```

Matches nodes with both NVIDIA GPU and NVMe storage.

## Trait Registry

Maintain a trait registry in your deployment repository documenting all traits in use.

**Example: `$UC_DEPLOY/docs/traits.md`**

```markdown
# Hardware Traits Registry

## Standard Traits
- NVME: NVMe storage present
- GPU_NVIDIA: NVIDIA GPU present
- NIC_MELLANOX: Mellanox NIC present

## Custom Traits
- GEN10: HP Gen10 server hardware
```

Benefits:

* Central documentation of all traits
* Discovery logic references
* Cross-team communication
* Audit trail for trait additions

## Integration with Flavors

The complete hardware matching flow:

1. **Inspection**: Ironic inspector discovers hardware, inspection hooks add traits
2. **Resource Class**: Inspection hook matches device-type and sets `node.resource_class`
3. **Trait Set**: Inspection hook sets `node.traits` based on discovered capabilities
4. **Flavor Matching**: Flavor definitions filter nodes by `resource_class` + trait requirements
5. **Nova Flavor**: Nova flavor created with properties from device-type resource class

Example end-to-end:

**Hardware**: Dell R7615 with 32 cores, 256GB RAM, NVMe, NVIDIA GPU

**Inspection discovers**:

* Device-type: Dell PowerEdge R7615
* Resource class: m1.medium (matched by CPU/RAM)
* Traits: NVME, GPU, GPU_NVIDIA

**Flavor matches**:

```yaml
name: compute.gpu-nvme
resource_class: m1.medium
traits:
  - trait: GPU_NVIDIA
    state: required
  - trait: NVME
    state: required
```

**Result**: Node eligible for `compute.gpu-nvme` flavor, Nova flavor created with m1.medium resource class properties (32 vCPUs, 256GB RAM from device-type).

## Trait Evolution

As deployments mature, custom traits may become standard traits:

1. **Custom trait usage**: Site adds `CUSTOM_NETWORK_ACCEL` for SmartNIC hardware
2. **Cross-site adoption**: Other sites implement same trait
3. **Standardization**: Trait documented as standard `NIC_SMARTNIC`
4. **Migration**: Update inspection hooks and flavor definitions to use standard name

Maintain backward compatibility during transitions by supporting both trait names temporarily.
