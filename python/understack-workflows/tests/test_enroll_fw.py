from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from ironicclient.common.apiclient import exceptions as ironic_exceptions

from understack_workflows.main import enroll_fw

BASE_ARGS: dict[str, Any] = {
    "name": "PA1410-026701008071",
    "physical_network": "f20-1-network",
    "resource_class": "pa1410",
    "ports": [
        {
            "label": "ethernet1/19",
            "mac": "60:15:2b:33:31:22",
            "switch": "n11-22-1.dfw3",
            "intf": "Ethernet1/43",
        }
    ],
}

FW_FIELDS: dict[str, Any] = {
    "management_ip": "10.15.149.46",
    "management_switch": "n11-22-1d.dfw3",
    "management_switch_port": "Ethernet1/24",
    "mate_serial": "026701010045",
}


def _node(
    *,
    driver: str = "netdev",
    resource_class: str = "pa1410",
    provision_state: str = "active",
    driver_info: dict | None = None,
    extra: dict | None = None,
):
    return SimpleNamespace(
        uuid="node-uuid",
        name=BASE_ARGS["name"],
        driver=driver,
        resource_class=resource_class,
        provision_state=provision_state,
        driver_info=driver_info or {},
        extra=extra or {},
    )


def _actual_port(
    *,
    label: str = "ethernet1/19",
    mac: str = "60:15:2b:33:31:22",
    switch: str = "n11-22-1.dfw3",
    intf: str = "Ethernet1/43",
    physnet: str = "f20-1-network",
    switch_id: str = "00:00:00:00:00:00",
):
    """A node port matching the BASE_ARGS request (so no structural drift)."""
    return SimpleNamespace(
        uuid=f"port-{label}",
        name=f"{BASE_ARGS['name']}:{label}",
        address=mac,
        physical_network=physnet,
        category="network",
        local_link_connection={
            "switch_id": switch_id,
            "switch_info": switch,
            "port_id": intf,
        },
    )


def _mock_client(mocker, *, node=None, node_ports=None):
    client = MagicMock()
    if node is None:
        client.get_node.side_effect = ironic_exceptions.NotFound()
    else:
        client.get_node.return_value = node
    client.list_ports.return_value = node_ports or []
    mocker.patch.object(enroll_fw, "IronicClient", return_value=client)
    return client


def _patch_paths(update_node_call) -> dict[str, Any]:
    (_uuid, patch), _ = update_node_call
    return {op["path"]: op["value"] for op in patch}


# --- enrollment path (new / re-enrollable node) -----------------------------


def test_enroll_fw_hands_metadata_to_the_engine(mocker):
    _mock_client(mocker, node=None)  # not found -> new node -> engine enrolls
    engine = mocker.patch.object(enroll_fw.netdev_reconciler, "enroll")

    enroll_fw.enroll_fw(**BASE_ARGS, **FW_FIELDS)

    engine.assert_called_once_with(
        name="PA1410-026701008071",
        physical_network="f20-1-network",
        ports=BASE_ARGS["ports"],
        resource_class="pa1410",
        external_cmdb_id=None,
        driver_info={
            "management_ip": "10.15.149.46",
            "management_switch": "n11-22-1d.dfw3",
            "management_switch_port": "Ethernet1/24",
        },
        extra={"mate_serial": "026701010045"},
    )


def test_enroll_fw_without_fw_fields_passes_empty_metadata(mocker):
    _mock_client(mocker, node=None)
    engine = mocker.patch.object(enroll_fw.netdev_reconciler, "enroll")

    enroll_fw.enroll_fw(**BASE_ARGS)

    _, kwargs = engine.call_args
    assert kwargs["driver_info"] == {}
    assert kwargs["extra"] == {}


def test_existing_non_active_node_delegates_to_engine(mocker):
    # A found-but-available node is re-enrollable, so it is handed to the engine
    # rather than treated as in-service.
    _mock_client(mocker, node=_node(provision_state="available"))
    engine = mocker.patch.object(enroll_fw.netdev_reconciler, "enroll")

    enroll_fw.enroll_fw(**BASE_ARGS, **FW_FIELDS)

    engine.assert_called_once()


def test_enroll_fw_rejects_generic_and_empty_resource_class(mocker):
    engine = mocker.patch.object(enroll_fw.netdev_reconciler, "enroll")

    for bad in ("", "   ", "generic", "GENERIC", " generic "):
        args = {**BASE_ARGS, "resource_class": bad}
        with pytest.raises(ValueError, match="purpose-made"):
            enroll_fw.enroll_fw(**args, **FW_FIELDS)

    # Rejected before the engine (or any Ironic call) is ever invoked.
    engine.assert_not_called()


def test_enroll_fw_normalizes_resource_class_whitespace(mocker):
    _mock_client(mocker, node=None)
    engine = mocker.patch.object(enroll_fw.netdev_reconciler, "enroll")
    args = {**BASE_ARGS, "resource_class": "  pa1410  "}

    enroll_fw.enroll_fw(**args, **FW_FIELDS)

    assert engine.call_args.kwargs["resource_class"] == "pa1410"


# --- in-service (active) node: metadata-only in place -----------------------


def test_active_node_updates_metadata_when_ports_match(mocker):
    client = _mock_client(mocker, node=_node(), node_ports=[_actual_port()])
    engine = mocker.patch.object(enroll_fw.netdev_reconciler, "enroll")

    enroll_fw.enroll_fw(**BASE_ARGS, **FW_FIELDS)

    engine.assert_not_called()
    client.update_node.assert_called_once()
    paths = _patch_paths(client.update_node.call_args)
    assert paths["/driver_info/management_ip"] == "10.15.149.46"
    assert paths["/extra/mate_serial"] == "026701010045"


def test_active_node_records_external_cmdb_id(mocker):
    client = _mock_client(mocker, node=_node(), node_ports=[_actual_port()])
    mocker.patch.object(enroll_fw.netdev_reconciler, "enroll")

    enroll_fw.enroll_fw(**BASE_ARGS, **FW_FIELDS, external_cmdb_id=12345)

    paths = _patch_paths(client.update_node.call_args)
    assert paths["/extra/external_cmdb_id"] == 12345


def test_active_node_noop_when_metadata_already_matches(mocker):
    node = _node(
        driver_info={
            "management_ip": "10.15.149.46",
            "management_switch": "n11-22-1d.dfw3",
            "management_switch_port": "Ethernet1/24",
        },
        extra={"mate_serial": "026701010045"},
    )
    client = _mock_client(mocker, node=node, node_ports=[_actual_port()])
    mocker.patch.object(enroll_fw.netdev_reconciler, "enroll")

    enroll_fw.enroll_fw(**BASE_ARGS, **FW_FIELDS)

    client.update_node.assert_not_called()


def test_active_node_rejects_port_connection_drift(mocker):
    # switch_info differs from the request -> the port would be updated.
    drifted = _actual_port(switch="some-other-switch.dfw3")
    client = _mock_client(mocker, node=_node(), node_ports=[drifted])
    engine = mocker.patch.object(enroll_fw.netdev_reconciler, "enroll")

    with pytest.raises(RuntimeError, match="in-service firewall"):
        enroll_fw.enroll_fw(**BASE_ARGS, **FW_FIELDS)

    engine.assert_not_called()
    client.update_node.assert_not_called()


def test_active_node_rejects_physical_network_drift(mocker):
    drifted = _actual_port(physnet="some-other-network")
    client = _mock_client(mocker, node=_node(), node_ports=[drifted])
    mocker.patch.object(enroll_fw.netdev_reconciler, "enroll")

    with pytest.raises(RuntimeError, match="in-service firewall"):
        enroll_fw.enroll_fw(**BASE_ARGS, **FW_FIELDS)

    client.update_node.assert_not_called()


def test_active_node_rejects_missing_port(mocker):
    # Node has no port matching the requested label -> it would be created.
    client = _mock_client(mocker, node=_node(), node_ports=[])
    mocker.patch.object(enroll_fw.netdev_reconciler, "enroll")

    with pytest.raises(RuntimeError, match="in-service firewall"):
        enroll_fw.enroll_fw(**BASE_ARGS, **FW_FIELDS)

    client.update_node.assert_not_called()


def test_active_node_rejects_non_netdev_driver(mocker):
    client = _mock_client(
        mocker, node=_node(driver="ipmi"), node_ports=[_actual_port()]
    )
    mocker.patch.object(enroll_fw.netdev_reconciler, "enroll")

    with pytest.raises(RuntimeError, match="non-netdev"):
        enroll_fw.enroll_fw(**BASE_ARGS, **FW_FIELDS)

    client.update_node.assert_not_called()


def test_active_node_rejects_resource_class_change(mocker):
    client = _mock_client(
        mocker, node=_node(resource_class="pa5410"), node_ports=[_actual_port()]
    )
    mocker.patch.object(enroll_fw.netdev_reconciler, "enroll")

    with pytest.raises(RuntimeError, match="resource_class"):
        enroll_fw.enroll_fw(**BASE_ARGS, **FW_FIELDS)

    client.update_node.assert_not_called()


# --- argument parsing -------------------------------------------------------


def test_argument_parser_requires_resource_class():
    parser = enroll_fw.argument_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "--name",
                "fw1",
                "--physical-network",
                "net",
                "--ports",
                "[]",
            ]
        )
