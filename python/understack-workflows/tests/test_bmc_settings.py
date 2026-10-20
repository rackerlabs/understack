from understack_workflows import bmc_settings
from understack_workflows.bmc import Bmc

MANAGER_ATTRIBUTES_PATH = (
    "/redfish/v1/Managers/iDRAC.Embedded.1/Oem/Dell/DellAttributes/iDRAC.Embedded.1"
)
UNCONFIGURED_IPV4 = "0.0.0.0"  # noqa: S104 -- value returned by iDRAC


def _current_attribute_values():
    return {
        key: value
        for key, value in bmc_settings.REQUIRED_VALUES.items()
        if value is not None
    }


def test_update_dell_drac_settings_uses_static_attributes_for_idrac10_dns(mocker):
    mocker.patch.dict(
        bmc_settings.REQUIRED_VALUES,
        {
            "IPv4.1.DNS1": "10.0.0.53",
            "IPv4.1.DNS2": "10.0.0.54",
        },
    )
    mocker.patch.dict(
        bmc_settings.VALUES_TO_POST,
        {
            "IPv4.1.DNS1": "10.0.0.53",
            "IPv4.1.DNS2": "10.0.0.54",
        },
    )
    bmc = mocker.Mock(spec=Bmc)
    bmc.manager_attributes_path = MANAGER_ATTRIBUTES_PATH
    bmc.redfish_request.side_effect = [
        {
            "Attributes": _current_attribute_values()
            | {
                "IPv4.1.DNS1": UNCONFIGURED_IPV4,
                "IPv4.1.DNS2": UNCONFIGURED_IPV4,
                "IPv4.1.StaticDNS1": UNCONFIGURED_IPV4,
                "IPv4.1.StaticDNS2": UNCONFIGURED_IPV4,
            }
        },
        {},
    ]

    changes = bmc_settings.update_dell_drac_settings(bmc)

    assert changes == {
        "IPv4.1.StaticDNS1": "10.0.0.53",
        "IPv4.1.StaticDNS2": "10.0.0.54",
    }
    assert bmc.redfish_request.call_args_list == [
        mocker.call(MANAGER_ATTRIBUTES_PATH),
        mocker.call(
            MANAGER_ATTRIBUTES_PATH,
            payload={
                "Attributes": {
                    "IPv4.1.StaticDNS1": "10.0.0.53",
                    "IPv4.1.StaticDNS2": "10.0.0.54",
                }
            },
            method="PATCH",
        ),
    ]


def test_update_dell_drac_settings_keeps_legacy_idrac9_dns_patch(mocker):
    attribute_path = "/redfish/v1/Managers/iDRAC.Embedded.1/Attributes"
    mocker.patch.dict(
        bmc_settings.REQUIRED_VALUES,
        {
            "IPv4.1.DNS1": "10.0.0.53",
            "IPv4.1.DNS2": "10.0.0.54",
        },
    )
    mocker.patch.dict(
        bmc_settings.VALUES_TO_POST,
        {
            "IPv4.1.DNS1": "10.0.0.53",
            "IPv4.1.DNS2": "10.0.0.54",
        },
    )
    current_values = _current_attribute_values() | {
        "IPv4.1.DNS1": UNCONFIGURED_IPV4,
        "IPv4.1.DNS2": UNCONFIGURED_IPV4,
    }
    bmc = mocker.Mock(spec=Bmc)
    bmc.manager_attributes_path = attribute_path
    bmc.redfish_request.side_effect = [{"Attributes": current_values}, {}]

    changes = bmc_settings.update_dell_drac_settings(bmc)

    expected_changes = {
        "IPv4.1.DNS1": "10.0.0.53",
        "IPv4.1.DNS2": "10.0.0.54",
    }
    assert changes == expected_changes
    bmc.redfish_request.assert_has_calls(
        [
            mocker.call(attribute_path),
            mocker.call(
                attribute_path,
                payload={"Attributes": expected_changes},
                method="PATCH",
            ),
        ]
    )
