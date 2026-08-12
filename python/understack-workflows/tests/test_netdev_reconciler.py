import logging
from types import SimpleNamespace
from unittest.mock import MagicMock
from unittest.mock import call

import pytest
from ironicclient.common.apiclient import exceptions as ironic_exceptions

from understack_workflows import ironic_node
from understack_workflows import netdev_reconciler

ENROLL_ARGS = {
    "name": "leaf01",
    "physical_network": "f20-1-network",
    "ports": [
        {
            "label": "port1",
            "mac": "00:11:22:33:44:55",
            "switch": "spine01.example.net",
            "intf": "Ethernet1/1",
        },
        {
            "label": "port2",
            "mac": "00:11:22:33:44:66",
            "switch": "spine02.example.net",
            "intf": "Ethernet1/2",
        },
    ],
}


def make_ironic_client():
    fake_client = MagicMock()
    node = SimpleNamespace(uuid="node-123", driver="netdev", provision_state="enroll")
    fake_client.node.get.side_effect = ironic_exceptions.NotFound()
    fake_client.node.create.return_value = node
    fake_client.port.list.return_value = []
    fake_client.port.create.side_effect = [
        SimpleNamespace(uuid="port-1"),
        SimpleNamespace(uuid="port-2"),
    ]
    return fake_client, node


def existing_port(label, mac, switch, interface, name=None, category="network"):
    return SimpleNamespace(
        uuid=f"uuid-{label}",
        address=mac,
        name=name or f"leaf01:{label}",
        physical_network="f20-1-network",
        category=category,
        local_link_connection={
            "switch_id": "00:00:00:00:00:00",
            "switch_info": switch,
            "port_id": interface,
        },
    )


def matching_ports():
    """Two existing ports that exactly match the ENROLL_ARGS request."""
    return [
        existing_port(
            "port1", "00:11:22:33:44:55", "spine01.example.net", "Ethernet1/1"
        ),
        existing_port(
            "port2", "00:11:22:33:44:66", "spine02.example.net", "Ethernet1/2"
        ),
    ]


def test_enroll_creates_node_ports_logs_and_makes_available(mocker, caplog):
    caplog.set_level(logging.INFO)
    fake_ironic, node = make_ironic_client()
    mocker.patch(
        "understack_workflows.ironic.client.get_ironic_client",
        return_value=fake_ironic,
    )

    netdev_reconciler.enroll(**ENROLL_ARGS, resource_class=None)

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

    netdev_reconciler.enroll(
        **ENROLL_ARGS,
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


def test_enroll_writes_driver_info_and_extra_on_create(mocker):
    fake_ironic, _ = make_ironic_client()
    mocker.patch(
        "understack_workflows.ironic.client.get_ironic_client",
        return_value=fake_ironic,
    )

    netdev_reconciler.enroll(
        **ENROLL_ARGS,
        driver_info={"management_ip": "10.0.0.1"},
        extra={"mate_serial": "MATE-1"},
    )

    fake_ironic.node.create.assert_called_once_with(
        automated_clean=False,
        driver="netdev",
        name="leaf01",
        resource_class="generic",
        driver_info={"management_ip": "10.0.0.1"},
        extra={"mate_serial": "MATE-1"},
    )


def test_enroll_patches_driver_info_and_extra_on_existing_node(mocker):
    fake_ironic, _ = make_ironic_client()
    fake_ironic.node.get.side_effect = None
    fake_ironic.node.get.return_value = SimpleNamespace(
        uuid="node-123",
        driver="netdev",
        provision_state="manageable",
        resource_class="generic",
        driver_info={},
        extra={},
    )
    fake_ironic.port.list.return_value = matching_ports()
    mocker.patch(
        "understack_workflows.ironic.client.get_ironic_client",
        return_value=fake_ironic,
    )

    netdev_reconciler.enroll(
        **ENROLL_ARGS,
        driver_info={"management_ip": "10.0.0.1"},
        extra={"mate_serial": "MATE-1"},
    )

    fake_ironic.node.update.assert_called_once_with(
        "node-123",
        [
            {"op": "add", "path": "/driver_info/management_ip", "value": "10.0.0.1"},
            {"op": "add", "path": "/extra/mate_serial", "value": "MATE-1"},
        ],
    )


def test_enroll_patches_physical_network_drift_on_existing_port(mocker):
    fake_ironic, _ = make_ironic_client()
    fake_ironic.node.get.side_effect = None
    fake_ironic.node.get.return_value = SimpleNamespace(
        uuid="node-123",
        driver="netdev",
        provision_state="manageable",
        resource_class="generic",
        driver_info={},
        extra={},
    )
    # port1 matches the request except for physical_network.
    drifted = existing_port(
        "port1", "00:11:22:33:44:55", "spine01.example.net", "Ethernet1/1"
    )
    drifted.physical_network = "OLD-physnet"
    fake_ironic.port.list.return_value = [
        drifted,
        existing_port(
            "port2", "00:11:22:33:44:66", "spine02.example.net", "Ethernet1/2"
        ),
    ]
    mocker.patch(
        "understack_workflows.ironic.client.get_ironic_client",
        return_value=fake_ironic,
    )

    netdev_reconciler.enroll(**ENROLL_ARGS)

    fake_ironic.port.update.assert_called_once_with(
        "uuid-port1",
        [{"op": "add", "path": "/physical_network", "value": "f20-1-network"}],
    )


def test_enroll_reuses_existing_node_and_matching_ports(mocker):
    fake_ironic, _ = make_ironic_client()
    fake_ironic.node.get.side_effect = None
    fake_ironic.node.get.return_value = SimpleNamespace(
        uuid="node-123", driver="netdev", provision_state="manageable"
    )
    fake_ironic.port.list.return_value = matching_ports()
    mocker.patch(
        "understack_workflows.ironic.client.get_ironic_client",
        return_value=fake_ironic,
    )

    netdev_reconciler.enroll(**ENROLL_ARGS)

    fake_ironic.node.create.assert_not_called()
    fake_ironic.port.create.assert_not_called()
    fake_ironic.port.update.assert_not_called()
    fake_ironic.node.update.assert_called_once_with(
        "node-123",
        [{"op": "add", "path": "/resource_class", "value": "generic"}],
    )
    # Node was already manageable: no manage transition, only provide.
    fake_ironic.node.set_provision_state.assert_called_once_with(
        "node-123",
        "provide",
        cleansteps=None,
        runbook=None,
        disable_ramdisk=None,
    )


def test_enroll_updates_existing_port_and_creates_missing_one(mocker):
    fake_ironic, _ = make_ironic_client()
    fake_ironic.node.get.side_effect = None
    fake_ironic.node.get.return_value = SimpleNamespace(
        uuid="node-123", driver="netdev", provision_state="manageable"
    )
    stale_port1 = existing_port(
        "port1", "00:11:22:33:44:55", "old-switch.example.net", "Ethernet9/9"
    )
    fake_ironic.port.list.return_value = [stale_port1]
    mocker.patch(
        "understack_workflows.ironic.client.get_ironic_client",
        return_value=fake_ironic,
    )

    netdev_reconciler.enroll(**ENROLL_ARGS)

    fake_ironic.port.update.assert_called_once_with(
        "uuid-port1",
        [
            {
                "op": "add",
                "path": "/local_link_connection",
                "value": {
                    "switch_id": "00:00:00:00:00:00",
                    "switch_info": "spine01.example.net",
                    "port_id": "Ethernet1/1",
                },
            },
        ],
    )
    fake_ironic.port.create.assert_called_once_with(
        address="00:11:22:33:44:66",
        category="network",
        local_link_connection={
            "switch_id": "00:00:00:00:00:00",
            "switch_info": "spine02.example.net",
            "port_id": "Ethernet1/2",
        },
        name="leaf01:port2",
        node_uuid="node-123",
        physical_network="f20-1-network",
    )


def test_enroll_skips_transitions_when_node_already_available(mocker):
    fake_ironic, _ = make_ironic_client()
    fake_ironic.node.get.side_effect = None
    fake_ironic.node.get.return_value = SimpleNamespace(
        uuid="node-123", driver="netdev", provision_state="available"
    )
    fake_ironic.port.list.return_value = matching_ports()
    mocker.patch(
        "understack_workflows.ironic.client.get_ironic_client",
        return_value=fake_ironic,
    )

    netdev_reconciler.enroll(**ENROLL_ARGS)

    fake_ironic.node.set_provision_state.assert_not_called()
    fake_ironic.node.wait_for_provision_state.assert_not_called()


def test_enroll_steps_available_node_down_to_update_ports(mocker):
    fake_ironic, _ = make_ironic_client()
    fake_ironic.node.get.side_effect = None
    fake_ironic.node.get.return_value = SimpleNamespace(
        uuid="node-123", driver="netdev", provision_state="available"
    )
    # port1 needs an update; port2 already matches.
    stale_port1 = existing_port(
        "port1", "00:11:22:33:44:55", "old-switch.example.net", "Ethernet9/9"
    )
    fake_ironic.port.list.return_value = [
        stale_port1,
        existing_port(
            "port2", "00:11:22:33:44:66", "spine02.example.net", "Ethernet1/2"
        ),
    ]
    mocker.patch(
        "understack_workflows.ironic.client.get_ironic_client",
        return_value=fake_ironic,
    )

    netdev_reconciler.enroll(**ENROLL_ARGS)

    # Ironic forbids port connectivity changes while available, so the node is
    # stepped available -> manageable, the port is updated, then provided back.
    fake_ironic.node.set_provision_state.assert_has_calls(
        [
            call(
                "node-123",
                "manage",
                cleansteps=None,
                runbook=None,
                disable_ramdisk=None,
            ),
            call(
                "node-123",
                "provide",
                cleansteps=None,
                runbook=None,
                disable_ramdisk=None,
            ),
        ]
    )
    fake_ironic.port.update.assert_called_once()


def test_available_node_steps_down_before_metadata_patch(mocker):
    # Reused available node with BOTH a resource_class change and a pending port
    # change: the node must leave the pool (manage) BEFORE resource_class is
    # patched, so it never sits allocatable in the new pool with stale ports.
    fake_ironic, _ = make_ironic_client()
    fake_ironic.node.get.side_effect = None
    fake_ironic.node.get.return_value = SimpleNamespace(
        uuid="node-123",
        driver="netdev",
        provision_state="available",
        resource_class="old-class",
        driver_info={},
        extra={},
    )
    fake_ironic.port.list.return_value = [
        existing_port(
            "port1", "00:11:22:33:44:55", "old-switch.example.net", "Ethernet9/9"
        ),
        existing_port(
            "port2", "00:11:22:33:44:66", "spine02.example.net", "Ethernet1/2"
        ),
    ]
    mocker.patch(
        "understack_workflows.ironic.client.get_ironic_client",
        return_value=fake_ironic,
    )

    netdev_reconciler.enroll(**ENROLL_ARGS, resource_class="new-class")

    def first_index(predicate):
        for i, mock_call in enumerate(fake_ironic.mock_calls):
            if predicate(mock_call):
                return i
        return -1

    manage_idx = first_index(
        lambda c: c[0] == "node.set_provision_state"
        and len(c[1]) > 1
        and c[1][1] == "manage"
    )
    metadata_idx = first_index(lambda c: c[0] == "node.update")

    assert manage_idx != -1
    assert metadata_idx != -1
    assert manage_idx < metadata_idx  # step-down before the metadata patch


def test_enroll_is_true_noop_when_available_and_everything_matches(mocker):
    fake_ironic, _ = make_ironic_client()
    fake_ironic.node.get.side_effect = None
    fake_ironic.node.get.return_value = SimpleNamespace(
        uuid="node-123",
        driver="netdev",
        provision_state="available",
        resource_class="generic",
        extra={},
    )
    fake_ironic.port.list.return_value = matching_ports()
    mocker.patch(
        "understack_workflows.ironic.client.get_ironic_client",
        return_value=fake_ironic,
    )

    netdev_reconciler.enroll(**ENROLL_ARGS)

    # Nothing drifted: no metadata patch, no port work, no state churn.
    fake_ironic.node.update.assert_not_called()
    fake_ironic.port.update.assert_not_called()
    fake_ironic.port.create.assert_not_called()
    fake_ironic.node.set_provision_state.assert_not_called()


def test_enroll_updates_metadata_only_on_available_node(mocker, caplog):
    caplog.set_level(logging.INFO)
    fake_ironic, _ = make_ironic_client()
    fake_ironic.node.get.side_effect = None
    fake_ironic.node.get.return_value = SimpleNamespace(
        uuid="node-123",
        driver="netdev",
        provision_state="available",
        resource_class="old-class",
        extra={},
    )
    fake_ironic.port.list.return_value = matching_ports()
    mocker.patch(
        "understack_workflows.ironic.client.get_ironic_client",
        return_value=fake_ironic,
    )

    netdev_reconciler.enroll(**ENROLL_ARGS, resource_class="new-class")

    # resource_class changed: node is patched, but no port work and no
    # transition, and the log does not claim "nothing to do".
    fake_ironic.node.update.assert_called_once_with(
        "node-123",
        [{"op": "add", "path": "/resource_class", "value": "new-class"}],
    )
    fake_ironic.node.set_provision_state.assert_not_called()
    assert "nothing to do" not in caplog.text


def test_enroll_fails_on_existing_node_with_other_driver(mocker):
    fake_ironic, _ = make_ironic_client()
    fake_ironic.node.get.side_effect = None
    fake_ironic.node.get.return_value = SimpleNamespace(
        uuid="node-123", driver="idrac", provision_state="active"
    )
    mocker.patch(
        "understack_workflows.ironic.client.get_ironic_client",
        return_value=fake_ironic,
    )

    with pytest.raises(RuntimeError, match="refusing to enroll it as a netdev"):
        netdev_reconciler.enroll(**ENROLL_ARGS)

    fake_ironic.node.create.assert_not_called()
    fake_ironic.port.create.assert_not_called()


def test_enroll_fails_on_node_in_unexpected_state(mocker):
    fake_ironic, _ = make_ironic_client()
    fake_ironic.node.get.side_effect = None
    fake_ironic.node.get.return_value = SimpleNamespace(
        uuid="node-123", driver="netdev", provision_state="active"
    )
    fake_ironic.port.list.return_value = matching_ports()
    mocker.patch(
        "understack_workflows.ironic.client.get_ironic_client",
        return_value=fake_ironic,
    )

    with pytest.raises(RuntimeError, match="Cannot enroll node in provision_state"):
        netdev_reconciler.enroll(**ENROLL_ARGS)

    # State is checked before any mutation: node is not patched, no transitions.
    fake_ironic.node.update.assert_not_called()
    fake_ironic.node.set_provision_state.assert_not_called()


def test_enroll_rejects_duplicate_port_macs(mocker):
    fake_ironic, _ = make_ironic_client()
    mocker.patch(
        "understack_workflows.ironic.client.get_ironic_client",
        return_value=fake_ironic,
    )

    args = {
        **ENROLL_ARGS,
        "ports": [
            {
                "label": "port1",
                "mac": "00:11:22:33:44:55",
                "switch": "s1",
                "intf": "e1",
            },
            {
                "label": "port2",
                "mac": "00:11:22:33:44:55",
                "switch": "s2",
                "intf": "e2",
            },
        ],
    }

    with pytest.raises(ValueError, match="Duplicate MAC"):
        netdev_reconciler.enroll(**args)

    # Fail fast, before any Ironic calls.
    fake_ironic.node.get.assert_not_called()
    fake_ironic.node.create.assert_not_called()


def test_enroll_rejects_duplicate_port_labels(mocker):
    fake_ironic, _ = make_ironic_client()
    mocker.patch(
        "understack_workflows.ironic.client.get_ironic_client",
        return_value=fake_ironic,
    )

    args = {
        **ENROLL_ARGS,
        "ports": [
            {
                "label": "port1",
                "mac": "00:11:22:33:44:55",
                "switch": "s1",
                "intf": "e1",
            },
            {
                "label": "port1",
                "mac": "00:11:22:33:44:66",
                "switch": "s2",
                "intf": "e2",
            },
        ],
    }

    with pytest.raises(ValueError, match="Duplicate label"):
        netdev_reconciler.enroll(**args)

    # Fail fast, before any Ironic calls.
    fake_ironic.node.get.assert_not_called()
    fake_ironic.node.create.assert_not_called()


def test_enroll_creates_n_ports(mocker):
    fake_ironic, _ = make_ironic_client()
    fake_ironic.port.create.side_effect = [
        SimpleNamespace(uuid="port-1"),
        SimpleNamespace(uuid="port-2"),
        SimpleNamespace(uuid="port-3"),
    ]
    mocker.patch(
        "understack_workflows.ironic.client.get_ironic_client",
        return_value=fake_ironic,
    )

    netdev_reconciler.enroll(
        name="leaf01",
        physical_network="f20-1-network",
        ports=[
            {
                "label": "port1",
                "mac": "00:11:22:33:44:55",
                "switch": "s1",
                "intf": "Eth1/1",
            },
            {
                "label": "port2",
                "mac": "00:11:22:33:44:66",
                "switch": "s2",
                "intf": "Eth1/2",
            },
            {
                "label": "port3",
                "mac": "00:11:22:33:44:77",
                "switch": "s3",
                "intf": "Eth1/3",
            },
        ],
    )

    assert fake_ironic.port.create.call_count == 3
    created_names = [c.kwargs["name"] for c in fake_ironic.port.create.call_args_list]
    assert created_names == ["leaf01:port1", "leaf01:port2", "leaf01:port3"]


def test_enroll_warns_and_keeps_orphan_ports(mocker, caplog):
    caplog.set_level(logging.WARNING)
    fake_ironic, _ = make_ironic_client()
    fake_ironic.node.get.side_effect = None
    fake_ironic.node.get.return_value = SimpleNamespace(
        uuid="node-123", driver="netdev", provision_state="manageable"
    )
    orphan = existing_port(
        "port9", "00:99:99:99:99:99", "old.example.net", "Ethernet9/9"
    )
    fake_ironic.port.list.return_value = [*matching_ports(), orphan]
    mocker.patch(
        "understack_workflows.ironic.client.get_ironic_client",
        return_value=fake_ironic,
    )

    netdev_reconciler.enroll(**ENROLL_ARGS)

    fake_ironic.port.delete.assert_not_called()
    assert "name=leaf01:port9 mac=00:99:99:99:99:99" in caplog.text
    assert "not in the request by label" in caplog.text


def test_enroll_shrinking_ports_leaves_extra_as_orphan(mocker, caplog):
    caplog.set_level(logging.WARNING)
    fake_ironic, _ = make_ironic_client()
    fake_ironic.node.get.side_effect = None
    fake_ironic.node.get.return_value = SimpleNamespace(
        uuid="node-123", driver="netdev", provision_state="manageable"
    )
    # Node currently has 3 ports; the request only lists the first two.
    port3 = existing_port(
        "port3", "00:11:22:33:44:77", "spine03.example.net", "Ethernet1/3"
    )
    fake_ironic.port.list.return_value = [*matching_ports(), port3]
    mocker.patch(
        "understack_workflows.ironic.client.get_ironic_client",
        return_value=fake_ironic,
    )

    netdev_reconciler.enroll(**ENROLL_ARGS)

    # port3 is not in the request: warned about, left in place, not touched.
    fake_ironic.port.delete.assert_not_called()
    fake_ironic.port.update.assert_not_called()
    assert "name=leaf01:port3 mac=00:11:22:33:44:77" in caplog.text
    assert "not in the request by label" in caplog.text


def test_enroll_refuses_mac_move_to_existing_port(mocker):
    fake_ironic, _ = make_ironic_client()
    fake_ironic.node.get.side_effect = None
    fake_ironic.node.get.return_value = SimpleNamespace(
        uuid="node-123", driver="netdev", provision_state="manageable"
    )
    # Existing: port1=..:55, port2=..:66, port3=..:77 (named leaf01:port1/2/3).
    fake_ironic.port.list.return_value = [
        *matching_ports(),
        existing_port(
            "port3", "00:11:22:33:44:77", "spine03.example.net", "Ethernet1/3"
        ),
    ]
    mocker.patch(
        "understack_workflows.ironic.client.get_ironic_client",
        return_value=fake_ironic,
    )

    # Operator wants port3's MAC to become port2 while port3 still exists.
    # The workflow refuses to do an automatic label move/rename.
    args = {
        **ENROLL_ARGS,
        "ports": [
            {
                "label": "port1",
                "mac": "00:11:22:33:44:55",
                "switch": "spine01.example.net",
                "intf": "Ethernet1/1",
            },
            {
                "label": "port2",
                "mac": "00:11:22:33:44:77",
                "switch": "spine03.example.net",
                "intf": "Ethernet1/3",
            },
        ],
    }

    with pytest.raises(RuntimeError, match="already used by port uuid-port3"):
        netdev_reconciler.enroll(**args)

    fake_ironic.port.update.assert_not_called()
    fake_ironic.port.create.assert_not_called()


def test_build_netdev_ports_rejects_unknown_fields():
    with pytest.raises(ValueError, match="unknown field"):
        netdev_reconciler.build_netdev_ports(
            [
                {
                    "label": "uplink-a",
                    "mac": "00:11:22:33:44:55",
                    "switch": "s1",
                    "intf": "e1",
                    "description": "not supported",
                }
            ]
        )


def test_build_netdev_ports_requires_fields():
    with pytest.raises(ValueError, match="missing required field"):
        netdev_reconciler.build_netdev_ports([{"mac": "00:11:22:33:44:55"}])


def test_build_netdev_ports_rejects_non_string_field():
    # A non-string mac must fail with a clear error, not an AttributeError from
    # .lower() deeper in the pipeline.
    with pytest.raises(ValueError, match="must be strings"):
        netdev_reconciler.build_netdev_ports(
            [{"label": "p1", "mac": 123, "switch": "s", "intf": "e"}]
        )


def test_build_netdev_ports_rejects_non_string_switch_id():
    with pytest.raises(ValueError, match="switch_id must be a string"):
        netdev_reconciler.build_netdev_ports(
            [
                {
                    "label": "p1",
                    "mac": "00:11:22:33:44:55",
                    "switch": "s",
                    "intf": "e",
                    "switch_id": 123,
                }
            ]
        )


def test_build_netdev_ports_requires_non_empty():
    with pytest.raises(ValueError, match="At least one port"):
        netdev_reconciler.build_netdev_ports([])


def test_parse_ports_arg_rejects_non_json():
    with pytest.raises(ValueError, match="must be valid JSON"):
        netdev_reconciler.parse_ports_arg("not-json")


def test_parse_ports_arg_rejects_non_array():
    with pytest.raises(ValueError, match="must be a JSON array"):
        netdev_reconciler.parse_ports_arg('{"mac": "x"}')


def test_enroll_updates_existing_port_mac_by_label(mocker):
    fake_ironic, _ = make_ironic_client()
    fake_ironic.node.get.side_effect = None
    fake_ironic.node.get.return_value = SimpleNamespace(
        uuid="node-123", driver="netdev", provision_state="manageable"
    )
    fake_ironic.port.list.return_value = [
        existing_port(
            "port1", "00:aa:bb:cc:dd:ee", "spine01.example.net", "Ethernet1/1"
        ),
        existing_port(
            "port2", "00:11:22:33:44:66", "spine02.example.net", "Ethernet1/2"
        ),
    ]
    mocker.patch(
        "understack_workflows.ironic.client.get_ironic_client",
        return_value=fake_ironic,
    )

    netdev_reconciler.enroll(**ENROLL_ARGS)

    fake_ironic.port.update.assert_called_once_with(
        "uuid-port1",
        [{"op": "add", "path": "/address", "value": "00:11:22:33:44:55"}],
    )
    fake_ironic.port.create.assert_not_called()


def test_enroll_switch_id_override_on_create(mocker):
    fake_ironic, node = make_ironic_client()
    fake_ironic.port.create.side_effect = [SimpleNamespace(uuid="port-1")]
    mocker.patch(
        "understack_workflows.ironic.client.get_ironic_client",
        return_value=fake_ironic,
    )

    netdev_reconciler.enroll(
        name="leaf01",
        physical_network="f20-1-network",
        ports=[
            {
                "label": "port1",
                "mac": "00:11:22:33:44:55",
                "switch": "spine01.example.net",
                "intf": "Ethernet1/1",
                "switch_id": "aa:bb:cc:dd:ee:ff",
            }
        ],
    )

    fake_ironic.port.create.assert_called_once_with(
        address="00:11:22:33:44:55",
        category="network",
        local_link_connection={
            "switch_id": "aa:bb:cc:dd:ee:ff",
            "switch_info": "spine01.example.net",
            "port_id": "Ethernet1/1",
        },
        name="leaf01:port1",
        node_uuid=node.uuid,
        physical_network="f20-1-network",
    )


def test_enroll_switch_id_override_replaces_existing_value(mocker):
    fake_ironic, _ = make_ironic_client()
    fake_ironic.node.get.side_effect = None
    fake_ironic.node.get.return_value = SimpleNamespace(
        uuid="node-123", driver="netdev", provision_state="manageable"
    )
    # port1 already has a real switch_id; the operator corrects it explicitly.
    port1 = existing_port(
        "port1", "00:11:22:33:44:55", "spine01.example.net", "Ethernet1/1"
    )
    port1.local_link_connection = {
        "switch_id": "11:11:11:11:11:11",
        "switch_info": "spine01.example.net",
        "port_id": "Ethernet1/1",
    }
    fake_ironic.port.list.return_value = [
        port1,
        existing_port(
            "port2", "00:11:22:33:44:66", "spine02.example.net", "Ethernet1/2"
        ),
    ]
    mocker.patch(
        "understack_workflows.ironic.client.get_ironic_client",
        return_value=fake_ironic,
    )

    netdev_reconciler.enroll(
        name="leaf01",
        physical_network="f20-1-network",
        ports=[
            {
                "label": "port1",
                "mac": "00:11:22:33:44:55",
                "switch": "spine01.example.net",
                "intf": "Ethernet1/1",
                "switch_id": "aa:bb:cc:dd:ee:ff",
            },
            {
                "label": "port2",
                "mac": "00:11:22:33:44:66",
                "switch": "spine02.example.net",
                "intf": "Ethernet1/2",
            },
        ],
    )

    # Explicit switch_id wins over the existing real value.
    fake_ironic.port.update.assert_called_once_with(
        "uuid-port1",
        [
            {
                "op": "add",
                "path": "/local_link_connection",
                "value": {
                    "switch_id": "aa:bb:cc:dd:ee:ff",
                    "switch_info": "spine01.example.net",
                    "port_id": "Ethernet1/1",
                },
            }
        ],
    )


def test_enroll_updates_port_with_null_local_link_connection(mocker):
    fake_ironic, _ = make_ironic_client()
    fake_ironic.node.get.side_effect = None
    fake_ironic.node.get.return_value = SimpleNamespace(
        uuid="node-123", driver="netdev", provision_state="manageable"
    )
    port1 = existing_port(
        "port1", "00:11:22:33:44:55", "spine01.example.net", "Ethernet1/1"
    )
    port1.local_link_connection = None
    fake_ironic.port.list.return_value = [
        port1,
        existing_port(
            "port2", "00:11:22:33:44:66", "spine02.example.net", "Ethernet1/2"
        ),
    ]
    mocker.patch(
        "understack_workflows.ironic.client.get_ironic_client",
        return_value=fake_ironic,
    )

    netdev_reconciler.enroll(**ENROLL_ARGS)

    # Whole local_link_connection object is replaced, not nested keys, so the
    # patch is valid even though the existing value was null.
    fake_ironic.port.update.assert_called_once_with(
        "uuid-port1",
        [
            {
                "op": "add",
                "path": "/local_link_connection",
                "value": {
                    "switch_id": "00:00:00:00:00:00",
                    "switch_info": "spine01.example.net",
                    "port_id": "Ethernet1/1",
                },
            },
        ],
    )


def test_enroll_converges_existing_port_missing_category(mocker):
    fake_ironic, _ = make_ironic_client()
    fake_ironic.node.get.side_effect = None
    fake_ironic.node.get.return_value = SimpleNamespace(
        uuid="node-123", driver="netdev", provision_state="manageable"
    )
    port1 = existing_port(
        "port1", "00:11:22:33:44:55", "spine01.example.net", "Ethernet1/1"
    )
    port1.category = None
    fake_ironic.port.list.return_value = [
        port1,
        existing_port(
            "port2", "00:11:22:33:44:66", "spine02.example.net", "Ethernet1/2"
        ),
    ]
    mocker.patch(
        "understack_workflows.ironic.client.get_ironic_client",
        return_value=fake_ironic,
    )

    netdev_reconciler.enroll(**ENROLL_ARGS)

    fake_ironic.port.update.assert_called_once_with(
        "uuid-port1",
        [{"op": "add", "path": "/category", "value": "network"}],
    )


def test_enroll_preserves_real_switch_id_when_only_metadata_changes(mocker):
    fake_ironic, _ = make_ironic_client()
    fake_ironic.node.get.side_effect = None
    fake_ironic.node.get.return_value = SimpleNamespace(
        uuid="node-123", driver="netdev", provision_state="manageable"
    )
    # port1 already has a real switch_id and a stale switch_info/port_id.
    port1 = existing_port(
        "port1", "00:11:22:33:44:55", "old-switch.example.net", "Ethernet9/9"
    )
    port1.local_link_connection = {
        "switch_id": "aa:bb:cc:dd:ee:ff",
        "switch_info": "old-switch.example.net",
        "port_id": "Ethernet9/9",
    }
    fake_ironic.port.list.return_value = [
        port1,
        existing_port(
            "port2", "00:11:22:33:44:66", "spine02.example.net", "Ethernet1/2"
        ),
    ]
    mocker.patch(
        "understack_workflows.ironic.client.get_ironic_client",
        return_value=fake_ironic,
    )

    netdev_reconciler.enroll(**ENROLL_ARGS)

    # switch_info/port_id converge to the request, but the real switch_id is
    # kept rather than being reset to the placeholder.
    fake_ironic.port.update.assert_called_once_with(
        "uuid-port1",
        [
            {
                "op": "add",
                "path": "/local_link_connection",
                "value": {
                    "switch_id": "aa:bb:cc:dd:ee:ff",
                    "switch_info": "spine01.example.net",
                    "port_id": "Ethernet1/1",
                },
            },
        ],
    )


def test_enroll_does_not_touch_port_with_real_switch_id_and_matching_metadata(
    mocker,
):
    fake_ironic, _ = make_ironic_client()
    fake_ironic.node.get.side_effect = None
    fake_ironic.node.get.return_value = SimpleNamespace(
        uuid="node-123", driver="netdev", provision_state="available"
    )
    port1 = existing_port(
        "port1", "00:11:22:33:44:55", "spine01.example.net", "Ethernet1/1"
    )
    port1.local_link_connection = {
        "switch_id": "aa:bb:cc:dd:ee:ff",
        "switch_info": "spine01.example.net",
        "port_id": "Ethernet1/1",
    }
    fake_ironic.port.list.return_value = [
        port1,
        existing_port(
            "port2", "00:11:22:33:44:66", "spine02.example.net", "Ethernet1/2"
        ),
    ]
    mocker.patch(
        "understack_workflows.ironic.client.get_ironic_client",
        return_value=fake_ironic,
    )

    netdev_reconciler.enroll(**ENROLL_ARGS)

    # A real switch_id with otherwise-matching metadata is a no-op: no port
    # update and no state churn on the available node.
    fake_ironic.port.update.assert_not_called()
    fake_ironic.node.set_provision_state.assert_not_called()
