from understack_workflows import bmc_bios


def test_update_dell_bios_settings_skips_patch_when_desired_values_are_pending(mocker):
    bmc = mocker.Mock()
    bmc.system_path = "/redfish/v1/Systems/System.Embedded.1"
    bmc.redfish_request.side_effect = [
        {
            "Attributes": {
                "PxeDev1EnDis": "Disabled",
                "PxeDev1Interface": "NIC.Slot.1-1",
                "HttpDev1EnDis": "Disabled",
                "HttpDev1Interface": "NIC.Slot.1-1",
                "HttpDev1TlsMode": "TLS",
                "TimeZone": "Local",
                "OS-BMC.1.AdminState": "Enabled",
                "IPMILan.1.Enable": "Enabled",
            }
        },
        {"Attributes": bmc_bios.required_bios_settings(["NIC.Embedded.1-1-1"])},
    ]
    patch_bios_settings = mocker.patch.object(bmc_bios, "patch_bios_settings")

    result = bmc_bios.update_dell_bios_settings(bmc, ["NIC.Embedded.1-1-1"])

    assert result == {}
    patch_bios_settings.assert_not_called()


def test_update_dell_bios_settings_only_patches_settings_not_already_pending(mocker):
    bmc = mocker.Mock()
    bmc.system_path = "/redfish/v1/Systems/System.Embedded.1"
    bmc.redfish_request.side_effect = [
        {
            "Attributes": {
                "PxeDev1EnDis": "Enabled",
                "PxeDev1Interface": "NIC.Slot.1-1",
                "HttpDev1EnDis": "Disabled",
                "HttpDev1Interface": "NIC.Slot.1-1",
                "HttpDev1TlsMode": "TLS",
                "TimeZone": "UTC",
                "OS-BMC.1.AdminState": "Enabled",
                "IPMILan.1.Enable": "Disabled",
            }
        },
        {
            "Attributes": {
                "PxeDev1EnDis": "Enabled",
                "PxeDev1Interface": "NIC.Embedded.1-1-1",
                "TimeZone": "UTC",
                "IPMILan.1.Enable": "Disabled",
            }
        },
    ]
    patch_bios_settings = mocker.patch.object(bmc_bios, "patch_bios_settings")

    result = bmc_bios.update_dell_bios_settings(bmc, ["NIC.Embedded.1-1-1"])

    assert result == {
        "HttpDev1EnDis": "Enabled",
        "HttpDev1Interface": "NIC.Embedded.1-1-1",
        "HttpDev1TlsMode": "None",
        "OS-BMC.1.AdminState": "Disabled",
        "PxeDev1EnDis": "Disabled",
    }
    patch_bios_settings.assert_called_once_with(bmc, result)
