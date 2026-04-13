from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock
from unittest.mock import call

from ironicclient.common.apiclient import exceptions as ironic_exceptions
from ironicclient.v1.node import Node

from understack_workflows.bmc import RedfishRequestError
from understack_workflows.bmc_chassis_info import ChassisInfo
from understack_workflows.bmc_chassis_info import InterfaceInfo
from understack_workflows.main import enroll_server


def make_device_info(
    *,
    power_on: bool,
    connected_mac: str | None = None,
    serial_number: str = "ABC123",
) -> ChassisInfo:
    return ChassisInfo(
        manufacturer="Dell",
        model_number="R760",
        serial_number=serial_number,
        bmc_ip_address="10.0.0.10",
        bios_version="1.0.0",
        power_on=power_on,
        memory_gib=64,
        cpu="Xeon",
        interfaces=[
            InterfaceInfo("iDRAC", "bmc", "00:00:00:00:00:01"),
            InterfaceInfo(
                "NIC.Integrated.1-1",
                "PXE NIC",
                "00:00:00:00:00:02",
                remote_switch_mac_address=connected_mac,
                remote_switch_port_name="Ethernet1/1" if connected_mac else None,
            ),
        ],
    )


def make_bmc(mocker, fake_sushy=None):
    bmc = mocker.MagicMock()
    bmc.ip_address = "10.0.0.10"
    bmc.username = "root"
    bmc.password = "calvin"
    bmc.url.return_value = "https://10.0.0.10"
    bmc.get_system_path.return_value = "/redfish/v1/Systems/System.Embedded.1"
    if fake_sushy is not None:
        bmc.sushy.return_value = fake_sushy
    return bmc


def make_raid_hardware():
    controller = SimpleNamespace(
        identity="RAID.Integrated.1-1",
        drives=[SimpleNamespace(identity="Disk1"), SimpleNamespace(identity="Disk2")],
    )
    system = SimpleNamespace(storage=SimpleNamespace(get_members=lambda: [controller]))
    return SimpleNamespace(
        get_system_collection=lambda: SimpleNamespace(get_members=lambda: [system])
    )


def make_ironic_client(
    *,
    node_name: str,
    node_uuid: str = "node-123",
    existing_node=None,
    inspect_interfaces: list[str] | None = None,
    traits: list[str] | None = None,
    runbook_ids: dict[str, str] | None = None,
):
    if inspect_interfaces is None:
        inspect_interfaces = ["idrac-redfish", "idrac-redfish"]
    if traits is None:
        traits = []
    if runbook_ids is None:
        runbook_ids = {}

    created_node = SimpleNamespace(
        uuid=node_uuid,
        provision_state="enroll",
        driver="idrac",
        inspect_interface="idrac-redfish",
    )
    inspect_interface_iter = iter(inspect_interfaces)
    fake_client = MagicMock()
    fake_client.node.api.runbook.get.side_effect = lambda trait: SimpleNamespace(
        uuid=runbook_ids[trait]
    )
    fake_client.node.create.return_value = created_node
    fake_client.node.get_traits.return_value = traits

    def get_node(ident, fields=None):
        if ident == node_name and fields is None:
            if existing_node is None:
                raise ironic_exceptions.NotFound()
            return existing_node
        if ident == node_uuid and fields == ["driver"]:
            return SimpleNamespace(driver="idrac")
        if ident == node_uuid and fields == ["inspect_interface"]:
            return SimpleNamespace(inspect_interface=next(inspect_interface_iter))
        raise AssertionError(
            f"Unexpected node lookup ident={ident!r} fields={fields!r}"
        )

    fake_client.node.get.side_effect = get_node
    return fake_client, created_node


def test_enrol_happy_path_uses_real_ironic_workflow(mocker):
    initial_info = make_device_info(power_on=False, connected_mac=None)
    powered_info = make_device_info(
        power_on=True,
        connected_mac="AA:BB:CC:DD:EE:FF",
    )
    fake_bmc = make_bmc(mocker, fake_sushy=make_raid_hardware())
    fake_ironic, created_node = make_ironic_client(
        node_name="Dell-ABC123",
        inspect_interfaces=["idrac-redfish", "idrac-redfish"],
    )

    mocker.patch.object(enroll_server, "bmc_for_ip_address", return_value=fake_bmc)
    mocker.patch.object(
        enroll_server,
        "chassis_info",
        side_effect=[initial_info, powered_info],
    )
    set_bmc_password = mocker.patch.object(enroll_server, "set_bmc_password")
    update_dell_drac_settings = mocker.patch.object(
        enroll_server, "update_dell_drac_settings"
    )
    bmc_set_hostname = mocker.patch.object(enroll_server, "bmc_set_hostname")
    update_dell_bios_settings = mocker.patch.object(
        enroll_server, "update_dell_bios_settings"
    )
    sleep = mocker.patch.object(enroll_server.time, "sleep")
    mocker.patch(
        "understack_workflows.ironic.client.get_ironic_client",
        return_value=fake_ironic,
    )

    enroll_server.enrol(
        ip_address="10.0.0.10",
        firmware_update=False,
        raid_configure=True,
        pxe_switch_macs={"AA:BB:CC:DD:EE:FF"},
        old_password="old-password",
        external_cmdb_id="cmdb-1",
    )

    set_bmc_password.assert_called_once_with(
        ip_address="10.0.0.10",
        new_password="calvin",
        old_password="old-password",
    )
    update_dell_drac_settings.assert_called_once_with(fake_bmc)
    bmc_set_hostname.assert_called_once_with(fake_bmc, "None", "Dell-ABC123")
    assert update_dell_bios_settings.call_count == 2
    update_dell_bios_settings.assert_any_call(
        fake_bmc,
        pxe_interfaces=["NIC.Integrated.1-1"],
    )
    sleep.assert_called_once_with(120)

    fake_bmc.redfish_request.assert_called_once_with(
        path="/redfish/v1/Systems/System.Embedded.1/Actions/ComputerSystem.Reset",
        payload={"ResetType": "On"},
        method="POST",
    )
    fake_ironic.node.create.assert_called_once_with(
        name="Dell-ABC123",
        driver="idrac",
        driver_info={
            "redfish_address": "https://10.0.0.10",
            "redfish_verify_ca": False,
            "redfish_username": "root",
            "redfish_password": "calvin",
        },
        boot_interface="http-ipxe",
        inspect_interface="idrac-redfish",
        extra={
            "external_cmdb_id": "cmdb-1",
            "enrolled_pxe_ports": ["NIC.Integrated.1-1"],
        },
    )
    fake_ironic.node.set_target_raid_config.assert_called_once_with(
        created_node.uuid,
        {
            "logical_disks": [
                {
                    "controller": "RAID.Integrated.1-1",
                    "is_root_volume": True,
                    "physical_disks": ["Disk1", "Disk2"],
                    "raid_level": "1",
                    "size_gb": "MAX",
                }
            ]
        },
    )
    fake_ironic.node.set_provision_state.assert_has_calls(
        [
            call(
                created_node.uuid,
                "manage",
                cleansteps=None,
                runbook=None,
                disable_ramdisk=None,
            ),
            call(
                created_node.uuid,
                "clean",
                cleansteps=[
                    {"interface": "raid", "step": "delete_configuration"},
                    {"interface": "raid", "step": "create_configuration"},
                ],
                runbook=None,
                disable_ramdisk=True,
            ),
            call(
                created_node.uuid,
                "inspect",
                cleansteps=None,
                runbook=None,
                disable_ramdisk=None,
            ),
            call(
                created_node.uuid,
                "inspect",
                cleansteps=None,
                runbook=None,
                disable_ramdisk=None,
            ),
            call(
                created_node.uuid,
                "provide",
                cleansteps=None,
                runbook=None,
                disable_ramdisk=None,
            ),
        ]
    )
    expected_reset = [{"op": "remove", "path": "/inspect_interface"}]
    expected_agent = [{"op": "add", "path": "/inspect_interface", "value": "agent"}]
    assert fake_ironic.node.update.call_args_list == [
        call(created_node.uuid, expected_reset),
        call(created_node.uuid, expected_agent),
    ]


def test_power_on_and_wait_retries_temporary_redfish_503(mocker):
    initial_info = make_device_info(power_on=False, connected_mac=None)
    powered_info = make_device_info(
        power_on=True,
        connected_mac="AA:BB:CC:DD:EE:FF",
    )
    fake_bmc = make_bmc(mocker)
    sleep = mocker.patch.object(enroll_server.time, "sleep")
    mocker.patch.object(
        enroll_server,
        "chassis_info",
        side_effect=[
            RedfishRequestError(
                "BMC communications failure HTTP 503 Service Unavailable "
                "Base.1.12.ServiceTemporarilyUnavailable"
            ),
            powered_info,
        ],
    )

    result = enroll_server.power_on_and_wait(fake_bmc, initial_info)

    assert result is powered_info
    fake_bmc.redfish_request.assert_called_once_with(
        path="/redfish/v1/Systems/System.Embedded.1/Actions/ComputerSystem.Reset",
        payload={"ResetType": "On"},
        method="POST",
    )
    assert sleep.call_args_list == [call(120), call(30)]


def test_enrol_existing_failed_node_recovers_and_updates(mocker):
    device_info = make_device_info(
        power_on=True,
        connected_mac="AA:BB:CC:DD:EE:FF",
    )
    existing_node = SimpleNamespace(
        uuid="node-999",
        provision_state="inspect failed",
        driver="idrac",
        inspect_interface="idrac-redfish",
    )
    fake_bmc = make_bmc(mocker)
    fake_ironic, _ = make_ironic_client(
        node_name="Dell-ABC123",
        node_uuid="node-999",
        existing_node=existing_node,
        inspect_interfaces=["idrac-redfish", "idrac-redfish"],
    )

    mocker.patch.object(enroll_server, "bmc_for_ip_address", return_value=fake_bmc)
    mocker.patch.object(enroll_server, "chassis_info", return_value=device_info)
    mocker.patch.object(enroll_server, "set_bmc_password")
    mocker.patch.object(enroll_server, "update_dell_drac_settings")
    mocker.patch.object(enroll_server, "bmc_set_hostname")
    mocker.patch.object(enroll_server, "update_dell_bios_settings")
    mocker.patch(
        "understack_workflows.ironic.client.get_ironic_client",
        return_value=fake_ironic,
    )

    enroll_server.enrol(
        ip_address="10.0.0.10",
        firmware_update=False,
        raid_configure=False,
        pxe_switch_macs={"AA:BB:CC:DD:EE:FF"},
        old_password=None,
        external_cmdb_id="cmdb-1",
    )

    fake_ironic.node.create.assert_not_called()
    fake_ironic.node.set_target_raid_config.assert_not_called()
    fake_ironic.node.set_provision_state.assert_has_calls(
        [
            call(
                existing_node.uuid,
                "manage",
                cleansteps=None,
                runbook=None,
                disable_ramdisk=None,
            ),
            call(
                existing_node.uuid,
                "inspect",
                cleansteps=None,
                runbook=None,
                disable_ramdisk=None,
            ),
            call(
                existing_node.uuid,
                "inspect",
                cleansteps=None,
                runbook=None,
                disable_ramdisk=None,
            ),
            call(
                existing_node.uuid,
                "provide",
                cleansteps=None,
                runbook=None,
                disable_ramdisk=None,
            ),
        ]
    )
    update_patch = fake_ironic.node.update.call_args_list[0].args[1]
    assert {
        "op": "add",
        "path": "/extra/enrolled_pxe_ports",
        "value": ["NIC.Integrated.1-1"],
    } in update_patch


def test_apply_firmware_updates_runs_traits_in_numeric_order(mocker):
    fake_ironic, _ = make_ironic_client(
        node_name="unused",
        node_uuid="node-789",
        traits=[
            "CUSTOM_FIRMWARE_UPDATE_20_BIOS",
            "CUSTOM_FIRMWARE_UPDATE_3_NIC",
            "CUSTOM_FIRMWARE_UPDATE_100_STORAGE",
            "CUSTOM_UNRELATED",
        ],
        runbook_ids={
            "CUSTOM_FIRMWARE_UPDATE_3_NIC": "runbook-3",
            "CUSTOM_FIRMWARE_UPDATE_20_BIOS": "runbook-20",
            "CUSTOM_FIRMWARE_UPDATE_100_STORAGE": "runbook-100",
        },
    )
    mocker.patch(
        "understack_workflows.ironic.client.get_ironic_client",
        return_value=fake_ironic,
    )
    node = cast(Node, SimpleNamespace(uuid="node-789"))

    enroll_server.ironic_node.apply_firmware_updates(node)

    fake_ironic.node.api.runbook.get.assert_has_calls(
        [
            call("CUSTOM_FIRMWARE_UPDATE_3_NIC"),
            call("CUSTOM_FIRMWARE_UPDATE_20_BIOS"),
            call("CUSTOM_FIRMWARE_UPDATE_100_STORAGE"),
        ]
    )
    fake_ironic.node.set_provision_state.assert_has_calls(
        [
            call(
                "node-789",
                "clean",
                cleansteps=None,
                runbook="runbook-3",
                disable_ramdisk=None,
            ),
            call(
                "node-789",
                "clean",
                cleansteps=None,
                runbook="runbook-20",
                disable_ramdisk=None,
            ),
            call(
                "node-789",
                "clean",
                cleansteps=None,
                runbook="runbook-100",
                disable_ramdisk=None,
            ),
        ]
    )


def test_guess_pxe_interface_unknown_name_avoids_bmc_interface():
    device_info = ChassisInfo(
        manufacturer="Dell",
        model_number="R760",
        serial_number="ABC123",
        bmc_ip_address="1.2.3.4",
        bios_version="1.0.0",
        power_on=False,
        memory_gib=0,
        cpu="cpu",
        interfaces=[
            InterfaceInfo("iDRAC", "bmc", "00:00:00:00:00:01"),
            InterfaceInfo(
                "NIC.Custom.9-1",
                "custom nic",
                "00:00:00:00:00:02",
                remote_switch_mac_address="AA:BB:CC:DD:EE:FF",
            ),
        ],
    )

    assert enroll_server.guess_pxe_interfaces(device_info, {"AA:BB:CC:DD:EE:FF"}) == [
        "NIC.Custom.9-1"
    ]
