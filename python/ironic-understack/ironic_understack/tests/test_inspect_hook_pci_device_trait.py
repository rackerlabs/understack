# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import json

import ironic.objects
import pytest

from ironic_understack.hooks.inspect_hook_pci_device_trait import PciDeviceTraitHook

# Populate ironic.objects.TraitList so it can be patched below.
ironic.objects.register_all()

_INVENTORY = {
    "pci_devices": [
        {
            "vendor_id": "8086",
            "product_id": "2922",
            "class": "010601",
            "revision": "02",
            "bus": "0000:00:1f.2",
        },
        {
            "vendor_id": "8086",
            "product_id": "2918",
            "class": "060100",
            "revision": "02",
            "bus": "0000:00:1f.0",
        },
        {
            "vendor_id": "8086",
            "product_id": "2930",
            "class": "0c0500",
            "revision": "02",
            "bus": "0000:00:1f.3",
        },
        {
            "vendor_id": "1b36",
            "product_id": "000c",
            "class": "060400",
            "revision": "00",
            "bus": "0000:00:01.2",
        },
        {
            "vendor_id": "1b36",
            "product_id": "000c",
            "class": "060400",
            "revision": "00",
            "bus": "0000:00:01.0",
        },
        {
            "vendor_id": "1b36",
            "product_id": "000d",
            "class": "0c0330",
            "revision": "01",
            "bus": "0000:02:00.0",
        },
    ]
}

_ALIASES = {
    ("8086", "2922"): "Eighty Twenty-Two",
    ("8086", "2918"): "eighty.eighteen",
    ("1b36", "000c"): "OneBZeroC",
}


def _mock_task(mocker, existing_traits):
    mock_traits = mocker.Mock()
    mock_traits.get_trait_names.return_value = list(existing_traits)
    mock_context = mocker.Mock()
    mock_node = mocker.Mock(id=1234, uuid="node-uuid", traits=mock_traits)
    return mocker.Mock(node=mock_node, context=mock_context), mock_node, mock_context


def _configure_aliases(mocker, aliases=_ALIASES):
    entries = [
        json.dumps({"vendor_id": vendor, "product_id": product, "name": name})
        for (vendor, product), name in aliases.items()
    ]
    mocker.patch(
        "ironic_understack.hooks.inspect_hook_pci_device_trait."
        "CONF.ironic_understack.pci_device_alias",
        entries,
    )


def _mock_trait_create(mocker):
    return mocker.patch(
        "ironic_understack.hooks.inspect_hook_pci_device_trait.objects.TraitList.create"
    )


def test_adds_traits_for_configured_devices_and_counts_each_alias(mocker):
    _configure_aliases(mocker)
    mock_task, mock_node, mock_context = _mock_task(mocker, [])
    trait_create = _mock_trait_create(mocker)

    PciDeviceTraitHook()(mock_task, _INVENTORY, {})

    trait_create.assert_called_once_with(
        mock_context,
        1234,
        {
            "CUSTOM_PCI_1_EIGHTY_TWENTY_TWO",
            "CUSTOM_PCI_1_EIGHTY_EIGHTEEN",
            "CUSTOM_PCI_2_ONEBZEROC",
        },
    )
    mock_node.save.assert_called_once_with()


def test_replaces_stale_pci_traits_and_preserves_traits_outside_prefix(mocker):
    _configure_aliases(mocker)
    existing = [
        "CUSTOM_PCI_8_OLD_DEVICE",
        "CUSTOM_PCI_1_ONEBZEROC",
        "CUSTOM_FIRMWARE_UPDATE_R7615",
        "CUSTOM_NETGROUP_F20_1_NETWORK",
        "CUSTOM_NETWORK_SWITCH",
        "CUSTOM_STORAGE_SWITCH",
    ]
    mock_task, mock_node, mock_context = _mock_task(mocker, existing)
    trait_create = _mock_trait_create(mocker)

    PciDeviceTraitHook()(mock_task, _INVENTORY, {})

    trait_create.assert_called_once_with(
        mock_context,
        1234,
        {
            "CUSTOM_PCI_1_EIGHTY_TWENTY_TWO",
            "CUSTOM_PCI_1_EIGHTY_EIGHTEEN",
            "CUSTOM_PCI_2_ONEBZEROC",
            "CUSTOM_FIRMWARE_UPDATE_R7615",
            "CUSTOM_NETGROUP_F20_1_NETWORK",
            "CUSTOM_NETWORK_SWITCH",
            "CUSTOM_STORAGE_SWITCH",
        },
    )
    mock_node.save.assert_called_once_with()


def test_removes_owned_traits_when_no_configured_device_is_present(mocker):
    _configure_aliases(mocker)
    existing = {"CUSTOM_PCI_2_ONEBZEROC", "CUSTOM_NETWORK_SWITCH"}
    inventory = {"pci_devices": [{"vendor_id": "ffff", "product_id": "0001"}]}
    mock_task, mock_node, mock_context = _mock_task(mocker, existing)
    trait_create = _mock_trait_create(mocker)

    PciDeviceTraitHook()(mock_task, inventory, {})

    trait_create.assert_called_once_with(mock_context, 1234, {"CUSTOM_NETWORK_SWITCH"})
    mock_node.save.assert_called_once_with()


def test_leaves_current_traits_intact(mocker):
    _configure_aliases(mocker)
    existing = {
        "CUSTOM_PCI_1_EIGHTY_TWENTY_TWO",
        "CUSTOM_PCI_1_EIGHTY_EIGHTEEN",
        "CUSTOM_PCI_2_ONEBZEROC",
        "CUSTOM_NETWORK_SWITCH",
    }
    mock_task, mock_node, _mock_context = _mock_task(mocker, existing)
    trait_create = _mock_trait_create(mocker)

    PciDeviceTraitHook()(mock_task, _INVENTORY, {})

    trait_create.assert_not_called()
    mock_node.save.assert_not_called()


@pytest.mark.parametrize(
    "bad_entry",
    [
        "not JSON",
        "null",
        "[]",
        json.dumps({"vendor_id": "8086", "product_id": "2922"}),
        json.dumps({"vendor_id": "8086", "product_id": "2922", "name": 123}),
        json.dumps(
            {
                "vendor_id": "8086",
                "product_id": "2922",
                "name": "Device",
                "extra": "value",
            }
        ),
        json.dumps({"vendor_id": "8086", "product_id": "2922", "name": ""}),
        json.dumps({"vendor_id": "8086", "product_id": "2922", "name": " - / "}),
        json.dumps({"vendor_id": "8086", "product_id": "2922", "name": "a" * 243}),
    ],
)
def test_bad_config_is_ignored(mocker, bad_entry):
    mocker.patch(
        "ironic_understack.hooks.inspect_hook_pci_device_trait."
        "CONF.ironic_understack.pci_device_alias",
        [bad_entry],
    )
    mock_task, mock_node, _mock_context = _mock_task(
        mocker, {"CUSTOM_PCI_1_EXISTING", "CUSTOM_NETWORK_SWITCH"}
    )
    trait_create = _mock_trait_create(mocker)

    PciDeviceTraitHook()(mock_task, _INVENTORY, {})

    trait_create.assert_not_called()
    mock_node.save.assert_not_called()


def test_bad_config_entry_does_not_hide_good_entries(mocker):
    entries = [
        "not JSON",
        json.dumps(
            {
                "vendor_id": "8086",
                "product_id": "2922",
                "name": "Eighty Twenty-Two",
            }
        ),
    ]
    mocker.patch(
        "ironic_understack.hooks.inspect_hook_pci_device_trait."
        "CONF.ironic_understack.pci_device_alias",
        entries,
    )
    mock_task, mock_node, mock_context = _mock_task(mocker, [])
    trait_create = _mock_trait_create(mocker)

    PciDeviceTraitHook()(mock_task, _INVENTORY, {})

    trait_create.assert_called_once_with(
        mock_context, 1234, {"CUSTOM_PCI_1_EIGHTY_TWENTY_TWO"}
    )
    mock_node.save.assert_called_once_with()


def test_skips_trait_that_becomes_overlong_when_device_count_is_added(mocker):
    _configure_aliases(mocker, {("8086", "2922"): "a" * 242})
    inventory = {
        "pci_devices": [
            {"vendor_id": "8086", "product_id": "2922"} for _index in range(10)
        ]
    }
    mock_task, mock_node, _mock_context = _mock_task(mocker, [])
    trait_create = _mock_trait_create(mocker)
    log_error = mocker.patch(
        "ironic_understack.hooks.inspect_hook_pci_device_trait.LOG.error"
    )

    PciDeviceTraitHook()(mock_task, inventory, {})

    trait_create.assert_not_called()
    mock_node.save.assert_not_called()
    log_error.assert_called_once()


def test_no_config_leaves_traits_intact(mocker):
    _configure_aliases(mocker, {})
    existing = {"CUSTOM_PCI_1_EXISTING", "CUSTOM_NETWORK_SWITCH"}
    mock_task, mock_node, _mock_context = _mock_task(mocker, existing)
    trait_create = _mock_trait_create(mocker)

    PciDeviceTraitHook()(mock_task, _INVENTORY, {})

    trait_create.assert_not_called()
    mock_node.save.assert_not_called()


@pytest.mark.parametrize("inventory", [{}, {"pci_devices": []}])
def test_no_pci_inventory_leaves_traits_intact(mocker, inventory):
    _configure_aliases(mocker)
    existing = {"CUSTOM_PCI_1_EXISTING", "CUSTOM_NETWORK_SWITCH"}
    mock_task, mock_node, _mock_context = _mock_task(mocker, existing)
    trait_create = _mock_trait_create(mocker)

    PciDeviceTraitHook()(mock_task, inventory, {})

    trait_create.assert_not_called()
    mock_node.save.assert_not_called()
