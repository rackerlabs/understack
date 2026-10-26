import argparse
import secrets
from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock
from unittest.mock import call

import pytest
from ironicclient.common.apiclient import exceptions as ironic_exceptions
from ironicclient.v1.node import Node

from understack_workflows.bmc_chassis_info import ChassisInfo
from understack_workflows.bmc_chassis_info import InterfaceInfo
from understack_workflows.ironic_node import NodeInterface
from understack_workflows.ironic_node import get_lldp_connected_interfaces
from understack_workflows.main import enroll_server


def random_mac() -> str:
    return ":".join(f"{b:02x}" for b in secrets.token_bytes(6))


DEFAULT_INTERFACE_NAMES = [
    "NIC.Embedded.1-1-1",
    "NIC.Embedded.2-1-1",
    "NIC.Integrated.1-2",
    "NIC.Integrated.1-1",
    "NIC.Slot.1-2",
    "NIC.Slot.1-1",
]


def make_node_inventory(
    *,
    interfaces: list[dict] | None = None,
    connected_interface_names: list[str] | None = None,
    serial_number: str = "FL6PC14",
    storage_controllers: list[dict] | None = None,
) -> dict:
    """Build a realistic Ironic node inventory dict, suitable for mocking."""
    if interfaces is None:
        interfaces = [
            {"mac_address": random_mac(), "name": name, "speed_mbps": 0}
            for name in DEFAULT_INTERFACE_NAMES
        ]
    if connected_interface_names is None:
        connected_interface_names = [iface["name"] for iface in interfaces]
    all_interfaces = {
        iface["name"]: {**iface, "pxe_enabled": False, "ipv6_address": None}
        for iface in interfaces
    }
    parsed_lldp = {
        name: {
            "switch_chassis_id": random_mac(),
            "switch_port_id": "Ethernet1/1",
        }
        for name in connected_interface_names
    }
    return {
        "inventory": {
            "interfaces": interfaces,
            "storage_controllers": storage_controllers or [],
            "system_vendor": {
                "product_name": "PowerEdge R7615",
                "serial_number": serial_number,
                "manufacturer": "Dell Inc.",
            },
        },
        "plugin_data": {
            "all_interfaces": all_interfaces,
            "parsed_lldp": parsed_lldp,
            "macs": [iface["mac_address"] for iface in interfaces],
        },
    }


def make_device_info(
    *,
    power_on: bool = True,
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
        bmc_interface=InterfaceInfo("iDRAC", "bmc", "00:00:00:00:00:01"),
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


def make_ironic_client(
    *,
    node_name: str,
    node_uuid: str = "node-123",
    existing_node=None,
    inspect_interfaces: list[str] | None = None,
    traits: list[str] | None = None,
    runbook_ids: dict[str, str] | None = None,
    inventory: dict | None = None,
    driver: str = "idrac",
    ports: list | None = None,
):
    if inspect_interfaces is None:
        inspect_interfaces = ["idrac-redfish"]
    if traits is None:
        traits = []
    if runbook_ids is None:
        runbook_ids = {}

    created_node = SimpleNamespace(
        uuid=node_uuid,
        provision_state="enroll",
        driver=driver,
        inspect_interface="idrac-redfish",
    )
    inspect_interface_iter = iter(inspect_interfaces)
    fake_client = MagicMock()
    fake_client.runbook.get.side_effect = lambda trait: SimpleNamespace(
        uuid=runbook_ids[trait]
    )
    fake_client.node.create.return_value = created_node
    fake_client.node.get_traits.return_value = traits
    if inventory is not None:
        fake_client.node.get_inventory.return_value = inventory
    fake_client.port.list.return_value = list(ports or [])

    def get_node(ident, fields=None):
        if ident == node_name and fields is None:
            if existing_node is None:
                raise ironic_exceptions.NotFound()
            return existing_node
        if ident == node_uuid and fields == ["driver"]:
            return SimpleNamespace(driver=driver)
        if ident == node_uuid and fields == ["inspect_interface"]:
            return SimpleNamespace(inspect_interface=next(inspect_interface_iter))
        raise AssertionError(
            f"Unexpected node lookup ident={ident!r} fields={fields!r}"
        )

    fake_client.node.get.side_effect = get_node
    return fake_client, created_node


def make_port(*, address: str, pxe_enabled: bool, bios_name: str | None):
    extra = {"bios_name": bios_name} if bios_name else {}
    return SimpleNamespace(
        address=address,
        pxe_enabled=pxe_enabled,
        extra=extra,
        physical_network="abc1234",
    )


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

    fake_ironic.runbook.get.assert_has_calls(
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


def test_get_node_interfaces_parses_inventory(mocker):
    mac1 = random_mac()
    mac2 = random_mac()
    inventory = make_node_inventory(
        interfaces=[
            {"name": "NIC.Embedded.1-1-1", "mac_address": mac1, "speed_mbps": 25000},
            {"name": "NIC.Slot.1-1", "mac_address": mac2, "speed_mbps": 0},
        ]
    )
    fake_ironic, node = make_ironic_client(
        node_name="Dell-TEST01",
        node_uuid="node-abc",
        inventory=inventory,
    )
    mocker.patch(
        "understack_workflows.ironic.client.get_ironic_client",
        return_value=fake_ironic,
    )

    result = enroll_server.ironic_node.get_node_interfaces(cast(Node, node))

    assert result == [
        NodeInterface(name="NIC.Embedded.1-1-1", mac_address=mac1, speed_mbps=25000),
        NodeInterface(name="NIC.Slot.1-1", mac_address=mac2, speed_mbps=0),
    ]
    fake_ironic.node.get_inventory.assert_called_once_with("node-abc")


def test_get_lldp_connected_interfaces_returns_matched():
    mac = random_mac()
    interfaces = [
        NodeInterface(name="NIC.Embedded.1-1-1", mac_address=mac, speed_mbps=0),
        NodeInterface(name="NIC.Slot.1-1", mac_address=random_mac(), speed_mbps=0),
    ]
    parsed_lldp = {
        "NIC.Embedded.1-1-1": {
            "switch_chassis_id": "aa:bb:cc:dd:ee:ff",
            "switch_port_id": "Ethernet1/5",
        },
    }

    result = get_lldp_connected_interfaces(interfaces, parsed_lldp)

    assert result == [
        NodeInterface(name="NIC.Embedded.1-1-1", mac_address=mac, speed_mbps=0)
    ]


def test_get_lldp_connected_interfaces_excludes_not_available():
    interfaces = [
        NodeInterface(name="NIC.Slot.1-1", mac_address=random_mac(), speed_mbps=0),
        NodeInterface(name="NIC.Slot.1-2", mac_address=random_mac(), speed_mbps=0),
    ]
    parsed_lldp = {
        "NIC.Slot.1-1": {
            "switch_chassis_id": "Not Available",
            "switch_port_id": "Not Available",
        },
        "NIC.Slot.1-2": {
            "switch_chassis_id": "Not Available",
            "switch_port_id": "Not Available",
        },
    }

    result = get_lldp_connected_interfaces(interfaces, parsed_lldp)

    assert result == []


def test_pxe_enabled_bios_name_filters_pxe_and_bios_name(mocker):
    fake_ironic, node = make_ironic_client(
        node_name="Dell-TEST01",
        node_uuid="node-abc",
        ports=[
            make_port(
                address="aa:01", pxe_enabled=True, bios_name="NIC.Integrated.1-1"
            ),
            make_port(address="aa:02", pxe_enabled=False, bios_name="NIC.Slot.1-1"),
            make_port(address="aa:03", pxe_enabled=True, bios_name=None),
            make_port(
                address="aa:04", pxe_enabled=True, bios_name="NIC.Integrated.1-2"
            ),
        ],
    )
    mocker.patch(
        "understack_workflows.ironic.client.get_ironic_client",
        return_value=fake_ironic,
    )

    result = enroll_server.ironic_node.pxe_enabled_bios_name(cast(Node, node))

    assert result == "NIC.Integrated.1-1"
    fake_ironic.port.list.assert_called_once_with(node="node-abc", detail=True)


def test_get_lldp_connected_interfaces_absent_from_lldp():
    interfaces = [
        NodeInterface(
            name="NIC.Embedded.2-1-1", mac_address=random_mac(), speed_mbps=0
        ),
    ]

    result = get_lldp_connected_interfaces(interfaces, parsed_lldp={})

    assert result == []


@pytest.mark.parametrize("runbooks", [None, [], ["first", "second"]])
def test_post_inspection_runbook_order(mocker, runbooks):
    node = SimpleNamespace(uuid="node-123")
    bmc = make_bmc(mocker)
    mocker.patch.object(enroll_server, "bmc_for_ip_address", return_value=bmc)
    # The trimmed enroll() derives the node name from a read-only chassis read.
    mocker.patch.object(enroll_server, "chassis_info", return_value=make_device_info())
    # RAID/firmware steps were removed from enroll(); keep apply_firmware_updates
    # patched so we can positively assert it is never called (flags are inert).
    apply_firmware_updates = mocker.patch.object(
        enroll_server.ironic_node, "apply_firmware_updates"
    )

    events = MagicMock()
    events.attach_mock(
        mocker.patch.object(
            enroll_server.ironic_node, "create_or_update", return_value=node
        ),
        "create_or_update",
    )
    for name in ("run_post_inspection_runbook", "transition"):
        events.attach_mock(mocker.patch.object(enroll_server.ironic_node, name), name)

    result = enroll_server.enroll(
        ip_address=bmc.ip_address,
        firmware_update=True,
        raid_configure=True,
        old_password=None,
        post_inspection_runbooks=runbooks,
    )

    expected = [
        call.create_or_update(
            bmc=bmc,
            name="Dell-ABC123",
            manufacturer="Dell",
            external_cmdb_id=None,
        )
    ]
    expected.extend(
        call.run_post_inspection_runbook(node, runbook) for runbook in runbooks or []
    )
    expected.append(
        call.transition(node, target_state="provide", expected_state="available")
    )
    assert events.mock_calls == expected
    assert result == node.uuid
    # firmware_update=True / raid_configure=True are inert in the trimmed flow.
    apply_firmware_updates.assert_not_called()


def test_post_inspection_runbook_uses_uuid_and_waits(mocker):
    client = mocker.patch.object(enroll_server.ironic_node, "IronicClient").return_value
    client.get_runbook.return_value = SimpleNamespace(
        uuid="runbook-123", traits=["CUSTOM_DELL", "CUSTOM_OTHER"], disable_ramdisk=True
    )
    client.get_node_traits.return_value = ["CUSTOM_DELL"]
    node = cast(Node, SimpleNamespace(uuid="node-123"))

    enroll_server.ironic_node.run_post_inspection_runbook(node, "post-inspection")

    client.get_runbook.assert_called_once_with("post-inspection")
    client.get_node_traits.assert_called_once_with(node.uuid)
    client.set_node_provision_state.assert_called_once_with(
        node.uuid,
        "clean",
        clean_steps=None,
        runbook="runbook-123",
        disable_ramdisk=None,
    )
    client.wait_for_node_provision_state.assert_called_once_with(
        node.uuid,
        "manageable",
        timeout=enroll_server.ironic_node.NODE_STATE_TIMEOUT_SECS,
    )


@pytest.mark.parametrize("traits", [[], ["CUSTOM_OTHER"], None])
def test_post_inspection_runbook_rejects_ineligible_node(mocker, traits):
    client = mocker.patch.object(enroll_server.ironic_node, "IronicClient").return_value
    client.get_runbook.return_value = SimpleNamespace(uuid="runbook-123", traits=traits)
    client.get_node_traits.return_value = ["CUSTOM_DELL"]
    node = cast(Node, SimpleNamespace(uuid="node-123"))

    with pytest.raises(ValueError, match=r"traits metadata|matching node trait"):
        enroll_server.ironic_node.run_post_inspection_runbook(node, "post-inspection")

    client.set_node_provision_state.assert_not_called()


def test_post_inspection_runbook_failure_propagates(mocker):
    client = mocker.patch.object(enroll_server.ironic_node, "IronicClient").return_value
    client.get_runbook.return_value = SimpleNamespace(
        uuid="runbook-123", traits=["CUSTOM_DELL"]
    )
    client.get_node_traits.return_value = ["CUSTOM_DELL"]
    client.wait_for_node_provision_state.side_effect = RuntimeError("clean failed")
    node = cast(Node, SimpleNamespace(uuid="node-123"))

    with pytest.raises(RuntimeError, match="clean failed"):
        enroll_server.ironic_node.run_post_inspection_runbook(node, "post-inspection")


def test_post_inspection_runbook_cli(mocker):
    mocker.patch(
        "sys.argv",
        [
            "enroll-server",
            "--ip-address",
            "10.0.0.10",
            "--post-inspection-runbooks",
            '["first", "second"]',
        ],
    )
    mocker.patch.object(enroll_server.helpers, "setup_logger")
    enroll = mocker.patch.object(enroll_server, "enroll")

    enroll_server.main()

    assert enroll.call_args.kwargs["post_inspection_runbooks"] == ["first", "second"]


@pytest.mark.parametrize(
    "value", ["invalid", '"first"', "{}", "null", "[null]", "[1]", '[""]', '[" "]']
)
def test_post_inspection_runbooks_reject_invalid_cli(value):
    with pytest.raises(argparse.ArgumentTypeError, match="JSON array"):
        enroll_server.parse_runbooks(value)


def test_post_inspection_runbooks_stop_on_failure(mocker):
    node = SimpleNamespace(uuid="node-123")
    mocker.patch.object(enroll_server, "bmc_for_ip_address")
    mocker.patch.object(enroll_server, "chassis_info", return_value=make_device_info())
    mocker.patch.object(
        enroll_server.ironic_node, "create_or_update", return_value=node
    )
    runbook = mocker.patch.object(
        enroll_server.ironic_node,
        "run_post_inspection_runbook",
        side_effect=RuntimeError("clean failed"),
    )
    transition = mocker.patch.object(enroll_server.ironic_node, "transition")

    with pytest.raises(RuntimeError, match="clean failed"):
        enroll_server.enroll(
            ip_address="10.0.0.10",
            firmware_update=True,
            raid_configure=True,
            old_password=None,
            post_inspection_runbooks=["first", "second"],
        )

    # The loop stops at the first failing runbook; transition never runs.
    runbook.assert_called_once_with(node, "first")
    transition.assert_not_called()


def test_main_emits_node_uuid_only_after_success(mocker, tmp_path):
    output = tmp_path / "node-uuid"
    mocker.patch(
        "sys.argv",
        [
            "enroll-server",
            "--ip-address",
            "192.0.2.1",
            "--node-uuid-output",
            str(output),
        ],
    )
    mocker.patch.object(enroll_server.helpers, "setup_logger")
    enroll = mocker.patch.object(enroll_server, "enroll", return_value="node-123")
    enroll_server.main()
    assert output.read_text() == "node-123\n"
    output.unlink()
    enroll.side_effect = RuntimeError("enrollment failed")
    with pytest.raises(RuntimeError, match="enrollment failed"):
        enroll_server.main()
    assert not output.exists()
