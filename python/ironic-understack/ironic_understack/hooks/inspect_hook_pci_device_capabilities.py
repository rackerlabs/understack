import collections

from ironic.drivers.modules.inspector.hooks import base
from oslo_log import log as logging

from ironic_understack.conf import CONF

LOG = logging.getLogger(__name__)

CAP_PREFIX = "pci_device_"


class PciDeviceCapabilitiesHook(base.InspectionHook):
    """Control a node's PCI device capabilities based on PCI device IDs.

    The hook reads configuration from the ``[ironic_understack]`` section of the
    config file:

    [ironic_understack]
    pci_device_capabilities = "{vendor_id:0x1002,product_id:0x75a8,name:amd_gpu_mi350p}"

    The Helm configuration for this looks like:

    pci_device_capabilities:
    - "{vendor_id:0x1002,product_id:0x75a8,name:amd_gpu_mi350p}"

    Upon inspection, a `capability` will be added to the node for each matching
    PCI device that is present in the inventory.

    Given the example above, if the node has a PCI card with vendor_id=0x1002
    product_id=0x75a8 then this hook will add a capability of
    "pci_device_amd_gpu_mi350p:1".

    The number is a count of those cards.  If two such cards are present in the
    server then the capability would read  "pci_device_amd_gpu_mi350p:2".

    All capabilities starting with "pci_device_" are owned by this hook.   This
    hook will clean up capabilities for PCI devices that are missing from
    inventory (or from the configuration!).   Capabilities that don't start with
    "pci_device_" are left untouched.
    """

    def __call__(self, task, inventory, plugin_data):
        """Set node capabilities for each applicable PCI device."""
        capability_names = configured_capability_names()
        if capability_names is None:
            return

        pci_devices = inventory.get("pci_devices")
        if not pci_devices:
            LOG.warning("No PCI device data is present in inventory")
            return

        current_capabilities = task.node.properties.get("capabilities", "")
        current_capabilities = (
            current_capabilities.split(",") if current_capabilities else []
        )

        required_capabilities = pci_device_capabilities(pci_devices, capability_names)

        new_capabilities = [
            k
            for k in current_capabilities
            if k in required_capabilities or not k.startswith(CAP_PREFIX)
        ] + [k for k in required_capabilities if k not in current_capabilities]

        task.node.set_property("capabilities", ",".join(new_capabilities))
        task.node.save()


def configured_capability_names() -> dict[str, str] | None:
    """Return configured PCI device capability names.

    An omitted option means that this hook is not configured.  An explicitly
    empty list intentionally removes any capabilities owned by this hook.
    """
    devices = CONF.ironic_understack.pci_device_capabilities
    if devices is None:
        LOG.debug("PCI device capabilities are not configured")
        return None

    capability_names = {}
    required_keys = {"vendor_id", "product_id", "name"}
    for index, device in enumerate(devices):
        if not isinstance(device, dict) or set(device) != required_keys:
            raise ValueError(
                f"PCI device capability entry {index} must contain exactly "
                "vendor_id, product_id, and name"
            )
        if not all(isinstance(device[key], str) for key in required_keys):
            raise ValueError(
                f"PCI device capability entry {index} must contain string values"
            )
        capability_names[pci_device_slug(device)] = device["name"]

    return capability_names


def pci_device_capabilities(
    pci_devices: list[dict[str, str]],
    capability_names: dict[str, str],
) -> set[str]:
    """Return capability strings such as ``pci_device_acme_coolkard:3``.

    This has the configured device name along with the number of such devices in
    this box.   We only include devices that appear in the capability_names
    dict.

    pci_devices is expected to be a list of devices like:

        [{"vendor_id": "0x1002", "product_id": "0x75a8", ...}, ...]

    capability_names is a dictionary mapping device ids to their names, like:

        {"1002:75a8": "amd_gpu_mi350p", ...}
    """
    pci_device_number_slugs = [pci_device_slug(dev) for dev in pci_devices]
    pci_device_names = [
        capability_names[key]
        for key in pci_device_number_slugs
        if key in capability_names
    ]
    return {
        f"{CAP_PREFIX}{name}:{count}"
        for name, count in collections.Counter(pci_device_names).items()
    }


def pci_device_slug(pci_device: dict[str, str]) -> str:
    """Return device ID in a format like "8086:4002"."""
    vendor_id = pci_device["vendor_id"].lower().removeprefix("0x")
    product_id = pci_device["product_id"].lower().removeprefix("0x")
    return f"{vendor_id}:{product_id}"
