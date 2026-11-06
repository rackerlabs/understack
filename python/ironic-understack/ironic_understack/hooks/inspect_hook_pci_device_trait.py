import collections
import json
import re

from ironic import objects
from ironic.drivers.modules.inspector.hooks import base
from oslo_log import log as logging

from ironic_understack.conf import CONF

LOG = logging.getLogger(__name__)

TRAIT_PREFIX = "CUSTOM_PCI_"
MAX_TRAIT_LENGTH = 255


class PciDeviceTraitHook(base.InspectionHook):
    """Control a node's PCI device traits based on PCI device IDs."""

    def __call__(self, task, inventory, plugin_data):
        _aliases = _parse_pci_alias_entries()
        if not _aliases:
            LOG.warning("No pci_device_alias configured under [inspector]")
            return

        pci_devices = inventory.get("pci_devices")
        if not pci_devices:
            LOG.warning("No PCI device data is present in inventory")
            return

        pci_device_keys = [(dev["vendor_id"], dev["product_id"]) for dev in pci_devices]
        known_pci_device_names = [
            _aliases[key] for key in pci_device_keys if key in _aliases
        ]
        required_traits = {
            f"{count}_{name}"
            for name, count in collections.Counter(known_pci_device_names).items()
        }

        _set_node_traits(task, required_traits)


def _parse_pci_alias_entries():
    parsed_pci_devices = []

    for pci_alias_entry in CONF.inspector.pci_device_alias:
        try:
            parsed_entry = json.loads(pci_alias_entry)
            required_keys = {"vendor_id", "product_id", "name"}
            if not isinstance(parsed_entry, dict) or set(parsed_entry) != required_keys:
                raise ValueError(
                    'The "pci_device_alias" entry should contain '
                    'exactly the "vendor_id", "product_id" and '
                    '"name" keys.'
                )
            if not all(isinstance(parsed_entry[key], str) for key in required_keys):
                raise ValueError(
                    'The "pci_device_alias" entry should contain string values.'
                )
            parsed_entry["name"] = _normalize_pci_alias_name(parsed_entry["name"])
            parsed_pci_devices.append(parsed_entry)
        except (TypeError, ValueError) as exc:
            LOG.error("Error parsing 'pci_device_alias' option: %s", exc)

    return {
        (dev["vendor_id"], dev["product_id"]): dev["name"] for dev in parsed_pci_devices
    }


def _normalize_pci_alias_name(name: str) -> str:
    """Return a predictable fragment suitable for an OpenStack custom trait."""
    normalized = re.sub(r"[^0-9A-Za-z]+", "_", name).strip("_").upper()
    if not normalized:
        raise ValueError(
            'The "name" in a "pci_device_alias" entry must contain at least '
            "one ASCII letter or digit."
        )

    # The smallest generated prefix includes the count ``1`` and its separator.
    if len(f"{TRAIT_PREFIX}1_{normalized}") > MAX_TRAIT_LENGTH:
        raise ValueError(
            'The normalized "name" in a "pci_device_alias" entry is too long '
            f"to fit in a {MAX_TRAIT_LENGTH}-character trait."
        )
    return normalized


def _set_node_traits(task, required_traits: set[str]):
    """Set a trait on the node for each recognised pci device.

    Manages only the ``{TRAIT_PREFIX}`` namespace: the required traits are
    added and any other ``{TRAIT_PREFIX}`` trait is removed. All other traits
    are left untouched.
    """
    required = set()
    for trait in required_traits:
        trait_name = TRAIT_PREFIX + trait
        if len(trait_name) > MAX_TRAIT_LENGTH:
            LOG.error(
                "Ignoring overlong PCI device trait %r; traits are limited to "
                "%d characters",
                trait_name,
                MAX_TRAIT_LENGTH,
            )
            continue
        required.add(trait_name)
    current = set(task.node.traits.get_trait_names())
    unmanaged = {t for t in current if not t.startswith(TRAIT_PREFIX)}
    required = required | unmanaged

    LOG.debug(
        "Checking traits for node %s: existing=%s required=%s",
        task.node.uuid,
        current,
        required,
    )
    if current != required:
        objects.TraitList.create(task.context, task.node.id, required)
        task.node.save()
