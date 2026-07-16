import logging
from types import SimpleNamespace
from unittest.mock import MagicMock
from unittest.mock import call

from understack_workflows import ironic_node
from understack_workflows.main import enroll_netdev


def make_ironic_client():
    fake_client = MagicMock()
    node = SimpleNamespace(uuid="node-123")
    fake_client.node.create.return_value = node
    fake_client.port.create.side_effect = [
        SimpleNamespace(uuid="port-1"),
        SimpleNamespace(uuid="port-2"),
    ]
    return fake_client, node


def test_enroll_creates_node_ports_logs_and_makes_available(mocker, caplog):
    caplog.set_level(logging.INFO)
    fake_ironic, node = make_ironic_client()
    mocker.patch(
        "understack_workflows.ironic.client.get_ironic_client",
        return_value=fake_ironic,
    )

    enroll_netdev.enroll(
        name="leaf01",
        physical_network="f20-1-network",
        port1_mac="00:11:22:33:44:55",
        port1_switch="spine01.example.net",
        port1_intf="Ethernet1/1",
        port2_mac="00:11:22:33:44:66",
        port2_switch="spine02.example.net",
        port2_intf="Ethernet1/2",
        resource_class=None,
    )

    fake_ironic.node.create.assert_called_once_with(
        automated_clean=False,
        driver="netdev",
        name="leaf01",
        resource_class="generic",
    )
    fake_ironic.port.create.assert_has_calls(
        [
            call(
                address="00:11:22:33:44:55",
                category="network",
                local_link_connection={
                    "switch_id": "00:00:00:00:00:00",
                    "switch_info": "spine01.example.net",
                    "port_id": "Ethernet1/1",
                },
                name="leaf01:port1",
                node_uuid=node.uuid,
                physical_network="f20-1-network",
            ),
            call(
                address="00:11:22:33:44:66",
                category="network",
                local_link_connection={
                    "switch_id": "00:00:00:00:00:00",
                    "switch_info": "spine02.example.net",
                    "port_id": "Ethernet1/2",
                },
                name="leaf01:port2",
                node_uuid=node.uuid,
                physical_network="f20-1-network",
            ),
        ]
    )
    fake_ironic.node.set_provision_state.assert_has_calls(
        [
            call(
                node.uuid,
                "manage",
                cleansteps=None,
                runbook=None,
                disable_ramdisk=None,
            ),
            call(
                node.uuid,
                "provide",
                cleansteps=None,
                runbook=None,
                disable_ramdisk=None,
            ),
        ]
    )
    fake_ironic.node.wait_for_provision_state.assert_has_calls(
        [
            call(
                node.uuid,
                "manageable",
                timeout=ironic_node.NODE_STATE_TIMEOUT_SECS,
            ),
            call(
                node.uuid,
                "available",
                timeout=ironic_node.NODE_STATE_TIMEOUT_SECS,
            ),
        ]
    )
    assert "Starting enroll-netdev workflow name=leaf01" in caplog.text
    assert "Created netdev Ironic node name=leaf01 uuid=node-123" in caplog.text
    assert "[node:node-123] Created baremetal port name=leaf01:port1" in caplog.text
    assert "[node:node-123] Node is available" in caplog.text


def test_enroll_records_external_cmdb_id_and_custom_resource_class(mocker):
    fake_ironic, _ = make_ironic_client()
    mocker.patch(
        "understack_workflows.ironic.client.get_ironic_client",
        return_value=fake_ironic,
    )

    enroll_netdev.enroll(
        name="leaf01",
        physical_network="f20-1-network",
        port1_mac="00:11:22:33:44:55",
        port1_switch="spine01.example.net",
        port1_intf="Ethernet1/1",
        port2_mac="00:11:22:33:44:66",
        port2_switch="spine02.example.net",
        port2_intf="Ethernet1/2",
        external_cmdb_id="cmdb-1",
        resource_class="switch",
    )

    fake_ironic.node.create.assert_called_once_with(
        automated_clean=False,
        driver="netdev",
        name="leaf01",
        resource_class="switch",
        extra={"external_cmdb_id": "cmdb-1"},
    )


def test_argument_parser_defaults_resource_class_to_generic():
    args = enroll_netdev.argument_parser().parse_args(
        [
            "--name",
            "leaf01",
            "--physical-network",
            "f20-1-network",
            "--port1-mac",
            "00:11:22:33:44:55",
            "--port1-switch",
            "spine01.example.net",
            "--port1-intf",
            "Ethernet1/1",
            "--port2-mac",
            "00:11:22:33:44:66",
            "--port2-switch",
            "spine02.example.net",
            "--port2-intf",
            "Ethernet1/2",
        ]
    )

    assert args.resource_class == "generic"
    assert args.external_cmdb_id == ""
