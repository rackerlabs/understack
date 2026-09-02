import logging

import ironic.objects

from ironic_understack.hooks.inspect_hook_chassis_model import InspectHookChassisModel

# Populate ironic.objects.TraitList so it can be patched below.
ironic.objects.register_all()

_INVENTORY = {
    "system_vendor": {
        "manufacturer": "Dell Inc.",
        "product_name": "PowerEdge R7615",
    }
}
_PLUGIN_DATA = {}


def _mock_task(mocker, existing_traits):
    mock_traits = mocker.Mock()
    mock_traits.get_trait_names.return_value = list(existing_traits)
    mock_context = mocker.Mock()
    mock_node = mocker.Mock(id=1234, uuid="node-uuid", traits=mock_traits)
    return mocker.Mock(node=mock_node, context=mock_context), mock_node, mock_context


def test_preserves_other_custom_traits(mocker, caplog):
    """Re-inspection must not wipe traits set by other hooks/rules."""
    caplog.set_level(logging.DEBUG)

    existing = [
        "CUSTOM_FIRMWARE_UPDATE_R7615",
        "CUSTOM_NETGROUP_F20_1_NETWORK",
        "CUSTOM_NETWORK_SWITCH",
        "CUSTOM_STORAGE_SWITCH",
    ]
    mock_task, mock_node, mock_context = _mock_task(mocker, existing)
    trait_create = mocker.patch(
        "ironic_understack.hooks.inspect_hook_chassis_model.objects.TraitList.create"
    )

    InspectHookChassisModel().__call__(mock_task, _INVENTORY, _PLUGIN_DATA)

    mock_node.save.assert_called_once()
    trait_create.assert_called_once_with(
        mock_context,
        1234,
        set(existing) | {"CUSTOM_CHASSIS_DELL_POWEREDGE_R7615"},
    )


def test_replaces_stale_chassis_trait(mocker):
    """A stale CUSTOM_CHASSIS_ trait is removed; other traits are kept."""
    existing = ["CUSTOM_NETWORK_SWITCH", "CUSTOM_CHASSIS_DELL_POWEREDGE_R6615"]
    mock_task, mock_node, mock_context = _mock_task(mocker, existing)
    trait_create = mocker.patch(
        "ironic_understack.hooks.inspect_hook_chassis_model.objects.TraitList.create"
    )

    InspectHookChassisModel().__call__(mock_task, _INVENTORY, _PLUGIN_DATA)

    mock_node.save.assert_called_once()
    trait_create.assert_called_once_with(
        mock_context,
        1234,
        {"CUSTOM_NETWORK_SWITCH", "CUSTOM_CHASSIS_DELL_POWEREDGE_R7615"},
    )
