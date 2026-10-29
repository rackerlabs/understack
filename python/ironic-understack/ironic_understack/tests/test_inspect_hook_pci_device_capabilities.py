from ironic_understack.hooks.inspect_hook_pci_device_capabilities import (
    PciDeviceCapabilitiesHook,
)
from ironic_understack.hooks.inspect_hook_pci_device_capabilities import (
    pci_device_capabilities,
)
from ironic_understack.hooks.inspect_hook_pci_device_capabilities import pci_device_slug

AMD_GPU = {
    "vendor_id": "0x1002",
    "product_id": "0x75a8",
    "name": "amd_gpu_mi350p",
}


def configure_pci_devices(mocker, *devices):
    mocker.patch(
        "ironic_understack.hooks.inspect_hook_pci_device_capabilities."
        "CONF.ironic_understack.pci_device_capabilities",
        list(devices),
    )


def test_adds_pci_capability_to_node_without_capabilities(mocker):
    configure_pci_devices(mocker, AMD_GPU)
    inventory = {
        "pci_devices": [
            {"vendor_id": "0x1002", "product_id": "0x75a8"},
            {"vendor_id": "0x1002", "product_id": "0x75a8"},
        ]
    }
    node = mocker.Mock(properties={})
    task = mocker.Mock(node=node)

    PciDeviceCapabilitiesHook()(task, inventory, {})

    node.set_property.assert_called_once_with(
        "capabilities", "pci_device_amd_gpu_mi350p:2"
    )
    node.save.assert_called_once_with()


def test_counts_all_matching_devices_from_redfish_inventory(mocker):
    configure_pci_devices(mocker, AMD_GPU)
    inventory = {
        "pci_devices": [
            {"vendor_id": "0x1002", "product_id": "0x75a8"},
            {"vendor_id": "0x1002", "product_id": "0x75a8"},
            {"vendor_id": "0x1002", "product_id": "0x75a8"},
            {"vendor_id": "0x1002", "product_id": "0x75a8"},
            {"vendor_id": "0x1002", "product_id": "0x75a8"},
            {"vendor_id": "0x1002", "product_id": "0x75a8"},
            {"vendor_id": "0x1002", "product_id": "0x75a8"},
            {"vendor_id": "0x1002", "product_id": "0x75a8"},
        ]
    }
    node = mocker.Mock(properties={})
    task = mocker.Mock(node=node)

    PciDeviceCapabilitiesHook()(task, inventory, {})

    node.set_property.assert_called_once_with(
        "capabilities", "pci_device_amd_gpu_mi350p:8"
    )
    node.save.assert_called_once_with()


def test_preserves_non_pci_capabilities(mocker):
    configure_pci_devices(mocker, AMD_GPU)
    inventory = {
        "pci_devices": [
            {"vendor_id": "0x1002", "product_id": "0x75a8"},
            {"vendor_id": "0x1002", "product_id": "0x75a8"},
        ]
    }
    node = mocker.Mock(properties={"capabilities": "boot_mode:uefi,profile:compute"})
    task = mocker.Mock(node=node)

    PciDeviceCapabilitiesHook()(task, inventory, {})

    node.set_property.assert_called_once_with(
        "capabilities",
        "boot_mode:uefi,profile:compute,pci_device_amd_gpu_mi350p:2",
    )
    node.save.assert_called_once_with()


def test_replaces_stale_pci_capability(mocker):
    configure_pci_devices(mocker, AMD_GPU)
    inventory = {
        "pci_devices": [
            {"vendor_id": "0x1002", "product_id": "0x75a8"},
            {"vendor_id": "0x1002", "product_id": "0x75a8"},
        ]
    }
    node = mocker.Mock(
        properties={"capabilities": "boot_mode:uefi,pci_device_amd_gpu_mi350p:1"}
    )
    task = mocker.Mock(node=node)

    PciDeviceCapabilitiesHook()(task, inventory, {})

    node.set_property.assert_called_once_with(
        "capabilities", "boot_mode:uefi,pci_device_amd_gpu_mi350p:2"
    )
    node.save.assert_called_once_with()


def test_does_not_duplicate_current_pci_capability(mocker):
    configure_pci_devices(mocker, AMD_GPU)
    inventory = {
        "pci_devices": [
            {"vendor_id": "0x1002", "product_id": "0x75a8"},
            {"vendor_id": "0x1002", "product_id": "0x75a8"},
        ]
    }
    node = mocker.Mock(properties={"capabilities": "pci_device_amd_gpu_mi350p:2"})
    task = mocker.Mock(node=node)

    PciDeviceCapabilitiesHook()(task, inventory, {})

    node.set_property.assert_called_once_with(
        "capabilities", "pci_device_amd_gpu_mi350p:2"
    )
    node.save.assert_called_once_with()


def test_removes_pci_capability_when_device_is_no_longer_present(mocker):
    configure_pci_devices(mocker, AMD_GPU)
    inventory = {
        "pci_devices": [
            {"vendor_id": "0x1022", "product_id": "0x7901"},
        ]
    }
    node = mocker.Mock(
        properties={"capabilities": "boot_mode:uefi,pci_device_amd_gpu_mi350p:2"}
    )
    task = mocker.Mock(node=node)

    PciDeviceCapabilitiesHook()(task, inventory, {})

    node.set_property.assert_called_once_with("capabilities", "boot_mode:uefi")
    node.save.assert_called_once_with()


def test_removes_pci_capability_when_device_is_no_longer_configured(mocker):
    configure_pci_devices(mocker)
    inventory = {
        "pci_devices": [
            {"vendor_id": "0x1002", "product_id": "0x75a8"},
        ]
    }
    node = mocker.Mock(properties={"capabilities": "pci_device_amd_gpu_mi350p:1"})
    task = mocker.Mock(node=node)

    PciDeviceCapabilitiesHook()(task, inventory, {})

    node.set_property.assert_called_once_with("capabilities", "")
    node.save.assert_called_once_with()


def test_does_nothing_when_inventory_has_no_pci_devices(mocker):
    configure_pci_devices(mocker, AMD_GPU)
    inventory = {}
    node = mocker.Mock(properties={})
    task = mocker.Mock(node=node)

    PciDeviceCapabilitiesHook()(task, inventory, {})

    node.set_property.assert_not_called()
    node.save.assert_not_called()


def test_does_nothing_when_pci_device_list_is_empty(mocker):
    configure_pci_devices(mocker, AMD_GPU)
    inventory = {"pci_devices": []}
    node = mocker.Mock(properties={})
    task = mocker.Mock(node=node)

    PciDeviceCapabilitiesHook()(task, inventory, {})

    node.set_property.assert_not_called()
    node.save.assert_not_called()


def test_does_nothing_when_configuration_is_omitted(mocker):
    mocker.patch(
        "ironic_understack.hooks.inspect_hook_pci_device_capabilities."
        "CONF.ironic_understack.pci_device_capabilities",
        None,
    )
    inventory = {"pci_devices": [{"vendor_id": "0x1002", "product_id": "0x75a8"}]}
    node = mocker.Mock(properties={"capabilities": "pci_device_old:1"})
    task = mocker.Mock(node=node)

    PciDeviceCapabilitiesHook()(task, inventory, {})

    node.set_property.assert_not_called()
    node.save.assert_not_called()


def test_counts_configured_pci_devices_and_ignores_other_devices():
    pci_devices = [
        {"vendor_id": "0x1002", "product_id": "0x75a8"},
        {"vendor_id": "0x1022", "product_id": "0x7901"},
        {"vendor_id": "0x1002", "product_id": "0x75a8"},
    ]
    capability_names = {"1002:75a8": "amd_gpu_mi350p"}

    capabilities = pci_device_capabilities(pci_devices, capability_names)

    assert capabilities == {"pci_device_amd_gpu_mi350p:2"}


def test_counts_device_ids_with_the_same_configured_name_together():
    pci_devices = [
        {"vendor_id": "0x1002", "product_id": "0x75a8"},
        {"vendor_id": "0x1002", "product_id": "0x75b0"},
    ]
    capability_names = {
        "1002:75a8": "amd_gpu",
        "1002:75b0": "amd_gpu",
    }

    capabilities = pci_device_capabilities(pci_devices, capability_names)

    assert capabilities == {"pci_device_amd_gpu:2"}


def test_pci_device_slug_removes_hexadecimal_prefixes():
    pci_device = {"vendor_id": "0x1002", "product_id": "0x75a8"}

    slug = pci_device_slug(pci_device)

    assert slug == "1002:75a8"


def test_pci_device_slug_accepts_ids_without_hexadecimal_prefixes():
    pci_device = {"vendor_id": "1002", "product_id": "75a8"}

    slug = pci_device_slug(pci_device)

    assert slug == "1002:75a8"


def test_pci_device_slug_normalizes_uppercase_ids():
    pci_device = {"vendor_id": "0X1002", "product_id": "0X75A8"}

    slug = pci_device_slug(pci_device)

    assert slug == "1002:75a8"
